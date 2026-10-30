"""Staff order detail: full submission view, artwork download, phase history."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.designs.models import Design
from apps.orders.design_details import parse_design_details
from apps.orders.models import Order, OrderPhaseChange, Payment, PaymentChannel

User = get_user_model()


def _png(name="img.png", size=(40, 40), color=(100, 100, 110)):
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class StaffOrderDetailTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="cust@example.com",
            password="x",
            role=User.Role.CUSTOMER,
            first_name="Casey",
            last_name="Customer",
            phone="09171234567",
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Varsity Tee",
            garment_template="tee",
            garment_color="navy",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {
                    "version": "6.6.1",
                    "objects": [
                        {
                            "type": "i-text",
                            "text": "HELLO",
                            "fontFamily": "Arial",
                            "fill": "#ffffff",
                        },
                        {
                            "type": "image",
                            "blytzName": "logo.png",
                            "src": "data:image/png;base64,xx",
                        },
                    ],
                },
                "views": {
                    "back": {
                        "version": "6.6.1",
                        "objects": [
                            {
                                "type": "textbox",
                                "text": "BACK TXT",
                                "fontFamily": "Georgia",
                                "fill": "#c9a227",
                            }
                        ],
                    }
                },
            },
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            canvas_json_snapshot=self.design.canvas_json,
            status=Order.Status.JOB_REQUEST,
            notes="Rush please",
            preview_image=_png("front.png", color=(20, 20, 30)),
            preview_back_image=_png("back.png", color=(30, 20, 20)),
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
            proof_file=_png("proof.png", color=(200, 162, 39)),
        )

    def test_staff_see_all_fields(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("staff_order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.order.order_id)
        self.assertContains(resp, "Varsity Tee")
        self.assertContains(resp, "tee")
        self.assertContains(resp, "navy")
        self.assertContains(resp, "Casey Customer")
        self.assertContains(resp, "cust@example.com")
        self.assertContains(resp, "09171234567")
        self.assertContains(resp, "Rush please")
        self.assertContains(resp, "HELLO")
        self.assertContains(resp, "BACK TXT")
        self.assertContains(resp, "logo.png")
        self.assertContains(resp, "Arial")
        self.assertContains(resp, "Front")
        self.assertContains(resp, "Back")
        self.assertContains(resp, "Download artwork (front)")
        self.assertContains(resp, "Download artwork (back)")
        self.assertContains(resp, self.order.preview_image.url)
        self.assertContains(resp, self.order.preview_back_image.url)
        # Job status and derived payment status shown separately.
        self.assertContains(resp, "Job Request")
        self.assertContains(resp, Order.OUTSTANDING)

    def test_customer_forbidden_on_staff_detail(self):
        self.client.force_login(self.customer)
        resp = self.client.get(
            reverse("staff_order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 403)

    def test_advance_does_not_alter_design_canvas(self):
        original = self.design.canvas_json
        self.client.force_login(self.staff)
        self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.design.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_EDIT)
        self.assertEqual(self.design.canvas_json, original)

    def test_pending_edit_shows_payment_proof(self):
        """Pending Edit layout must still expose payment proofs for review."""
        self.order.status = Order.Status.PENDING_EDIT
        self.order.save(update_fields=["status"])
        payment = self.order.payments.get()
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("staff_order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Final design")
        self.assertContains(resp, payment.proof_file.url)
        self.assertContains(resp, Order.OUTSTANDING)

    def test_customer_cannot_download_artwork(self):
        self.client.force_login(self.customer)
        for side in ("front", "back"):
            resp = self.client.get(
                reverse(
                    "download_order_preview",
                    kwargs={"order_id": self.order.order_id, "side": side},
                )
            )
            self.assertEqual(resp.status_code, 403)

        # Customer order page must not expose staff download links.
        detail = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Download artwork")
        self.assertNotContains(
            detail,
            reverse(
                "download_order_preview",
                kwargs={"order_id": self.order.order_id, "side": "front"},
            ),
        )

    def test_staff_can_download_artwork(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse(
                "download_order_preview",
                kwargs={"order_id": self.order.order_id, "side": "front"},
            )
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertIn("attachment", resp["Content-Disposition"])

        resp_back = self.client.get(
            reverse(
                "download_order_preview",
                kwargs={"order_id": self.order.order_id, "side": "back"},
            )
        )
        self.assertEqual(resp_back.status_code, 200)

    def test_phase_changes_are_recorded(self):
        self.client.force_login(self.staff)
        before = OrderPhaseChange.objects.filter(order=self.order).count()
        resp = self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            OrderPhaseChange.objects.filter(order=self.order).count(), before + 1
        )
        change = OrderPhaseChange.objects.filter(order=self.order).latest("changed_at")
        self.assertEqual(change.from_status, Order.Status.JOB_REQUEST)
        self.assertEqual(change.to_status, Order.Status.PENDING_EDIT)
        self.assertEqual(change.changed_by_id, self.staff.pk)

        page = self.client.get(
            reverse("staff_order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertContains(page, "Phase change history")
        self.assertContains(page, "Job Request")
        self.assertContains(page, "Pending Edit")

    def test_parse_design_details_unreadable(self):
        result = parse_design_details("not-a-dict")
        self.assertFalse(result["ok"])
        self.assertIn("could not be read", result["error"].lower())

        result2 = parse_design_details({"schema_version": 1, "canvas": "bad"})
        self.assertFalse(result2["ok"])


class DesignDetailsParseTests(TestCase):
    def test_parse_v1_envelope(self):
        snap = {
            "schema_version": 1,
            "canvas": {
                "objects": [
                    {
                        "type": "IText",
                        "text": "Hi",
                        "fontFamily": "Inter",
                        "fill": "#000",
                    }
                ]
            },
            "views": {"back": {"objects": []}},
        }
        result = parse_design_details(snap)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["views"]), 2)
        self.assertEqual(result["views"][0]["texts"], ["Hi"])
        self.assertEqual(result["views"][0]["fonts"], ["Inter"])
