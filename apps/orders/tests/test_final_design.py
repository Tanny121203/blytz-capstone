"""Final design upload, versioning, customer approval, and manual Production move."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.designs.models import ActivityLog, Design
from apps.orders.models import Order, OrderPhaseChange, Payment, PaymentChannel
from apps.orders.proof import validate_final_design_file
from apps.orders.views import STALE_FINAL_DESIGN_MESSAGE

User = get_user_model()


def _png(name="design.png", size=(48, 48), color=(40, 80, 120)):
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def _pdf(name="design.pdf"):
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
        content_type="application/pdf",
    )


class FinalDesignFlowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="owner@example.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="other@example.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Final Tee",
            canvas_json={},
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.PENDING_EDIT,
            preview_image=_png("front.png"),
            preview_back_image=_png("back.png", color=(20, 20, 20)),
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="0917",
            is_active=True,
        )
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("500.00"),
            status=Payment.Status.ACCEPTED,
        )

    def test_upload_sets_version_one(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("v1.png", color=(1, 2, 3))},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_design_version, 1)
        self.assertTrue(self.order.final_design)
        self.assertIsNotNone(self.order.final_design_uploaded_at)
        self.assertFalse(
            ActivityLog.objects.filter(
                order=self.order, kind=ActivityLog.Kind.DESIGN_REVISED
            ).exists()
        )

    def test_upload_replaces_file_and_bumps_version(self):
        self.client.force_login(self.staff)
        first = _png("first.png", color=(10, 10, 10))
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": first},
        )
        self.order.refresh_from_db()
        old_name = self.order.final_design.name
        self.assertEqual(self.order.final_design_version, 1)

        second = _png("second.png", color=(200, 10, 10))
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": second},
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_design_version, 2)
        self.assertNotEqual(self.order.final_design.name, old_name)
        self.assertTrue(
            ActivityLog.objects.filter(
                order=self.order, kind=ActivityLog.Kind.DESIGN_REVISED
            ).exists()
        )

    def test_customer_sees_final_design_immediately(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("show.png")},
        )
        self.order.refresh_from_db()

        self.client.force_login(self.customer)
        resp = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Final design")
        self.assertContains(resp, "Version 1")
        self.assertContains(resp, self.order.final_design.url)
        self.assertContains(resp, "Approve final design")

    def test_customer_sees_pdf_download_link(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _pdf()},
        )
        self.order.refresh_from_db()
        self.client.force_login(self.customer)
        resp = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertContains(resp, "Download final design (PDF)")
        self.assertContains(resp, self.order.final_design.url)

    def test_stale_version_approval_rejected(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("a.png")},
        )
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("b.png", color=(9, 9, 9))},
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_design_version, 2)

        self.client.force_login(self.customer)
        resp = self.client.post(
            reverse("approve_final_design", kwargs={"order_id": self.order.order_id}),
            {"version": 1},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_EDIT)
        self.assertIsNone(self.order.approved_version)

        page = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertContains(page, STALE_FINAL_DESIGN_MESSAGE)

    def test_approval_moves_to_production_and_logs(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("ok.png")},
        )
        self.order.refresh_from_db()

        self.client.force_login(self.customer)
        before_phase = OrderPhaseChange.objects.filter(order=self.order).count()
        resp = self.client.post(
            reverse("approve_final_design", kwargs={"order_id": self.order.order_id}),
            {"version": self.order.final_design_version},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PRODUCTION)
        self.assertEqual(self.order.approved_version, 1)
        self.assertIsNotNone(self.order.approved_at)
        self.assertEqual(
            OrderPhaseChange.objects.filter(order=self.order).count(),
            before_phase + 1,
        )
        change = OrderPhaseChange.objects.filter(order=self.order).latest("changed_at")
        self.assertEqual(change.from_status, Order.Status.PENDING_EDIT)
        self.assertEqual(change.to_status, Order.Status.PRODUCTION)
        self.assertTrue(
            ActivityLog.objects.filter(
                order=self.order, kind=ActivityLog.Kind.DESIGN_APPROVED
            ).exists()
        )

        page = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertNotContains(page, "Approve final design")

    def test_other_customer_cannot_approve(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("x.png")},
        )
        self.client.force_login(self.other)
        resp = self.client.post(
            reverse("approve_final_design", kwargs={"order_id": self.order.order_id}),
            {"version": 1},
        )
        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_EDIT)

    def test_customer_cannot_upload_final_design(self):
        self.client.force_login(self.customer)
        resp = self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("hack.png")},
        )
        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_design_version, 0)
        self.assertFalse(self.order.final_design)

    def test_staff_cannot_approve_final_design(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("y.png")},
        )
        resp = self.client.post(
            reverse("approve_final_design", kwargs={"order_id": self.order.order_id}),
            {"version": 1},
        )
        self.assertEqual(resp.status_code, 403)

    def test_upload_rejected_outside_pending_edit(self):
        self.order.status = Order.Status.PRODUCTION
        self.order.save(update_fields=["status"])
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("late.png")},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_design_version, 0)
        self.assertFalse(self.order.final_design)

    def test_manual_move_to_production_without_final_design(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PRODUCTION)
        self.assertFalse(self.order.final_design)

    def test_manual_move_to_production_with_final_design(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("upload_final_design", kwargs={"order_id": self.order.order_id}),
            {"final_design": _png("ready.png")},
        )
        resp = self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PRODUCTION)
        self.assertEqual(self.order.final_design_version, 1)
        self.assertIsNone(self.order.approved_version)

    def test_pending_edit_page_shows_upload_form(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("staff_order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Final design")
        self.assertContains(resp, "Upload final design")
        self.assertContains(
            resp, reverse("upload_final_design", kwargs={"order_id": self.order.order_id})
        )
        self.assertContains(resp, "Move to Production")

    def test_final_design_not_shrunk(self):
        """Final designs are stored as-is (unlike payment proofs)."""
        big = _png("big.png", size=(2200, 100), color=(5, 5, 5))
        raw_size = big.size
        validated = validate_final_design_file(big)
        self.assertEqual(validated.size, raw_size)
        with Image.open(validated) as img:
            self.assertEqual(img.size, (2200, 100))


@override_settings(PROOF_MAX_UPLOAD_MB=1)
class FinalDesignSizeLimitTests(TestCase):
    def test_oversized_final_design_rejected(self):
        from django import forms

        big = SimpleUploadedFile(
            "huge.png",
            b"0" * (2 * 1024 * 1024),
            content_type="image/png",
        )
        with self.assertRaises(forms.ValidationError) as ctx:
            validate_final_design_file(big)
        self.assertIn("1 MB", str(ctx.exception))
