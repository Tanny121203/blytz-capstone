import json
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from django.conf import settings

from apps.designs.models import ActivityLog, Design
from apps.orders.models import Order, Payment, PaymentChannel
from apps.sales.models import Lead

User = get_user_model()

# Supported Blytz schema v1 payload (matches editor persist contract).
SUBMIT_CANVAS_V1 = {
    "schema_version": 1,
    "width": 800,
    "height": 800,
    "canvas": {
        "version": "6.6.1",
        "objects": [{"type": "rect", "width": 10, "height": 10, "fill": "#111111"}],
    },
    "views": {"back": {"version": "6.6.1", "objects": []}},
}


def _png_file(name="proof.png", size=(32, 32), color=(200, 162, 39)):
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class DesignSubmitTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="buyer@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="other@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Test GCash",
            account_name="Blytz",
            account_number="09170001111",
            is_active=True,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Submit me",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {"version": "6.6.1", "objects": []},
                "views": {"back": {"version": "6.6.1", "objects": []}},
            },
        )

    def _submit(
        self,
        user=None,
        design=None,
        *,
        window_started_at=None,
        proof=None,
        preview_image=None,
        preview_back_image=None,
        amount="500.00",
        channel=None,
        omit_previews=False,
    ):
        user = user or self.customer
        design = design or self.design
        self.client.force_login(user)
        started = window_started_at or timezone.now().isoformat()
        data = {
            "channel": (channel or self.channel).pk,
            "amount_claimed": amount,
            "canvas_json": json.dumps(SUBMIT_CANVAS_V1),
            "window_started_at": started,
            "proof_file": proof if proof is not None else _png_file(),
        }
        if not omit_previews:
            data["preview_image"] = (
                preview_image
                if preview_image is not None
                else _png_file("preview_front.png", (48, 48), (40, 40, 40))
            )
            data["preview_back_image"] = (
                preview_back_image
                if preview_back_image is not None
                else _png_file("preview_back.png", (48, 48), (60, 60, 80))
            )
        return self.client.post(
            reverse("design_submit", args=[design.pk]),
            data,
        )

    def test_submission_creates_order_payment_lead_and_activity_logs(self):
        before_orders = Order.objects.count()
        before_payments = Payment.objects.count()
        before_leads = Lead.objects.count()
        before_logs = ActivityLog.objects.count()

        response = self._submit()
        order = Order.objects.get(design=self.design)

        self.assertRedirects(
            response,
            reverse("order_detail", kwargs={"order_id": order.order_id}),
        )
        self.assertEqual(Order.objects.count(), before_orders + 1)
        self.assertEqual(Payment.objects.count(), before_payments + 1)
        self.assertEqual(Lead.objects.count(), before_leads + 1)
        self.assertEqual(ActivityLog.objects.count(), before_logs + 2)

        payment = Payment.objects.get(order=order)
        lead = Lead.objects.get(order=order)
        self.assertEqual(payment.amount_claimed, Decimal("500.00"))
        self.assertEqual(payment.channel_id, self.channel.pk)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(order.total_paid, Decimal("0.00"))
        self.assertTrue(payment.proof_file)
        self.assertEqual(lead.stage, Lead.Stage.NEW_LEAD)
        self.assertEqual(
            order.canvas_json_snapshot["canvas"]["objects"][0]["type"], "rect"
        )
        self.assertTrue(order.preview_image)
        self.assertTrue(order.preview_back_image)
        kinds = set(
            ActivityLog.objects.filter(order=order).values_list("kind", flat=True)
        )
        self.assertEqual(
            kinds,
            {
                ActivityLog.Kind.DESIGN_SUBMITTED,
                ActivityLog.Kind.ORDER_CONFIRMED,
            },
        )

    def test_submission_stores_both_previews(self):
        front = _png_file("front.png", (64, 64), (10, 20, 30))
        back = _png_file("back.png", (64, 64), (30, 20, 10))
        response = self._submit(preview_image=front, preview_back_image=back)
        order = Order.objects.get(design=self.design)
        self.assertRedirects(
            response,
            reverse("order_detail", kwargs={"order_id": order.order_id}),
        )
        self.assertTrue(order.preview_image.name.endswith(".png"))
        self.assertTrue(order.preview_back_image.name.endswith(".png"))
        with order.preview_image.open("rb") as fh:
            img = Image.open(fh)
            img.load()
            self.assertEqual(img.format, "PNG")
        with order.preview_back_image.open("rb") as fh:
            img = Image.open(fh)
            img.load()
            self.assertEqual(img.format, "PNG")

    def test_bad_preview_rejected(self):
        bad = SimpleUploadedFile(
            "fake.png",
            b"not-a-real-png",
            content_type="image/png",
        )
        response = self._submit(preview_image=bad)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(design=self.design).exists())

        response = self._submit(omit_previews=True)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(design=self.design).exists())

    def test_expired_window_records_nothing(self):
        expired = (timezone.now() - timedelta(minutes=30)).isoformat()
        response = self._submit(window_started_at=expired)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(design=self.design).exists())
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Lead.objects.filter(customer=self.customer).exists())

    def test_cancelled_prompt_records_nothing(self):
        """Cancel never POSTs submit — save-only leaves no order/payment/lead."""
        self.client.force_login(self.customer)
        self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": '{"version":1,"objects":[],"saved":true}'},
        )
        self.design.refresh_from_db()
        self.assertTrue(self.design.canvas_json.get("saved"))
        self.assertFalse(Order.objects.filter(design=self.design).exists())
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Lead.objects.filter(customer=self.customer).count(), 0)

    def test_bad_file_types_rejected(self):
        bad = SimpleUploadedFile(
            "malware.exe",
            b"MZ\x00\x00not-an-image",
            content_type="application/octet-stream",
        )
        response = self._submit(proof=bad)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(design=self.design).exists())

        max_bytes = int(settings.PROOF_MAX_UPLOAD_MB) * 1024 * 1024
        big = SimpleUploadedFile(
            "big.png",
            b"0" * (max_bytes + 1),
            content_type="image/png",
        )
        response = self._submit(proof=big)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(design=self.design).exists())

    def test_customer_cannot_submit_another_customers_design(self):
        response = self._submit(user=self.other)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Order.objects.filter(design=self.design).exists())

    def test_second_submit_rejected_after_order_exists(self):
        """Server duplicate guard: once an order exists, further submits fail."""
        first = self._submit()
        order = Order.objects.get(design=self.design)
        self.assertRedirects(
            first,
            reverse("order_detail", kwargs={"order_id": order.order_id}),
        )
        before = Order.objects.filter(design=self.design).count()
        second = self._submit()
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Order.objects.filter(design=self.design).count(), before)

    def test_already_submitted_returns_json_for_xhr(self):
        """Stage I: AJAX retry after success must get JSON, not HTML redirect."""
        self._submit()
        self.assertTrue(self.design.is_submitted)
        self.client.force_login(self.customer)
        started = timezone.now().isoformat()
        response = self.client.post(
            reverse("design_submit", args=[self.design.pk]),
            {
                "channel": self.channel.pk,
                "amount_claimed": "500.00",
                "canvas_json": json.dumps(SUBMIT_CANVAS_V1),
                "window_started_at": started,
                "proof_file": _png_file(),
                "preview_image": _png_file("preview_front.png", (48, 48), (40, 40, 40)),
                "preview_back_image": _png_file(
                    "preview_back.png", (48, 48), (60, 60, 80)
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get("ok"))
        self.assertIn("design", data.get("errors", {}))
        self.assertEqual(Order.objects.filter(design=self.design).count(), 1)

    def test_submit_persists_posted_canvas_snapshot_not_prior_draft(self):
        """Invariant: order snapshot is the validated POST payload, not stale draft."""
        response = self._submit()
        order = Order.objects.get(design=self.design)
        self.assertRedirects(
            response,
            reverse("order_detail", kwargs={"order_id": order.order_id}),
        )
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json, SUBMIT_CANVAS_V1)
        self.assertEqual(order.canvas_json_snapshot, SUBMIT_CANVAS_V1)
        self.assertEqual(
            order.canvas_json_snapshot["canvas"]["objects"][0]["type"], "rect"
        )

    def test_editor_page_loads_for_owner(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="editor-root"')
        self.assertContains(response, "Strictly no refunds")
        self.assertContains(response, "editor_contract.js")
        self.assertContains(response, "fabric.min.js")
        self.assertContains(response, "blytz-fabric-canvas")
