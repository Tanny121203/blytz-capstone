import io
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.designs.models import Design
from apps.orders.models import Order, Payment, PaymentChannel
from apps.orders.proof import proof_max_bytes, validate_and_process_proof
from services.proof_images import MAX_PROOF_EDGE_PX, process_proof_file

User = get_user_model()


def _make_png_bytes(size=(100, 80), color=(10, 20, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_jpeg_with_exif_orientation():
    """JPEG with EXIF Orientation=6 (rotate 90 CW) and GPS-ish metadata."""
    img = Image.new("RGB", (120, 60), color=(255, 0, 0))
    # Paint a unique top-left pixel so orientation can be asserted after transpose.
    img.putpixel((0, 0), (0, 255, 0))
    exif = img.getexif()
    exif[274] = 6  # Orientation
    # GPS IFD tag
    exif[34853] = {1: "N", 2: (14.0, 0.0, 0.0)}
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95, exif=exif)
    return buffer.getvalue()


class ProofProcessingUnitTests(TestCase):
    def test_setting_drives_max_bytes(self):
        self.assertEqual(settings.PROOF_MAX_UPLOAD_MB, 15)
        self.assertEqual(proof_max_bytes(), 15 * 1024 * 1024)

    def test_15mb_accepted_16mb_rejected(self):
        ok = SimpleUploadedFile(
            "ok.png",
            b"0" * (15 * 1024 * 1024),
            content_type="image/png",
        )
        # Size check runs before image decode — oversized rejected first.
        big = SimpleUploadedFile(
            "big.png",
            b"0" * (16 * 1024 * 1024),
            content_type="image/png",
        )
        from django import forms

        with self.assertRaises(forms.ValidationError) as ctx:
            validate_and_process_proof(big)
        self.assertIn("15 MB", str(ctx.exception))

        # 15 MB of zeros is not a valid PNG — corrupt rejected after size OK.
        with self.assertRaises(forms.ValidationError) as ctx2:
            validate_and_process_proof(ok)
        self.assertIn("valid image", str(ctx2.exception).lower())

        real = SimpleUploadedFile(
            "real.png",
            _make_png_bytes(),
            content_type="image/png",
        )
        processed = validate_and_process_proof(real)
        self.assertTrue(processed.name.lower().endswith(".png"))

    def test_shrink_longest_side_and_strip_metadata(self):
        huge = SimpleUploadedFile(
            "huge.jpg",
            _make_jpeg_with_exif_orientation(),
            content_type="image/jpeg",
        )
        # Rebuild as a large image with orientation
        img = Image.new("RGB", (3000, 1000), color=(40, 40, 40))
        img.putpixel((0, 0), (0, 255, 0))
        exif = img.getexif()
        exif[274] = 6
        exif[34853] = {1: "N", 2: (1.0, 0.0, 0.0)}
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, exif=exif)
        huge = SimpleUploadedFile("huge.jpg", buf.getvalue(), content_type="image/jpeg")

        out = process_proof_file(huge)
        result = Image.open(out)
        result.load()
        self.assertLessEqual(max(result.size), MAX_PROOF_EDGE_PX)
        # Orientation applied: original 3000x1000 with orient 6 → ~1000x3000 then shrink
        self.assertLessEqual(result.size[0], MAX_PROOF_EDGE_PX)
        self.assertLessEqual(result.size[1], MAX_PROOF_EDGE_PX)
        # Metadata stripped
        self.assertFalse(result.getexif())
        self.assertNotIn(34853, result.getexif())
        # Output should be smaller than a naive high-quality 3000px JPEG
        self.assertLess(len(out.read()), len(buf.getvalue()))
        out.seek(0)

    def test_corrupt_image_rejected(self):
        from django import forms

        fake = SimpleUploadedFile(
            "fake.png",
            b"not-a-real-png-file",
            content_type="image/png",
        )
        with self.assertRaises(forms.ValidationError) as ctx:
            validate_and_process_proof(fake)
        self.assertIn("valid image", str(ctx.exception).lower())

    def test_pdf_untouched(self):
        raw = b"%PDF-1.4 fake content for test"
        pdf = SimpleUploadedFile("proof.pdf", raw, content_type="application/pdf")
        out = process_proof_file(pdf)
        out.seek(0)
        self.assertEqual(out.read(), raw)


@override_settings(PROOF_MAX_UPLOAD_MB=15)
class ProofUploadIntegrationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="proof@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="09175555555",
            is_active=True,
        )
        self.design = Design.objects.create(
            owner=self.customer, title="Proof design", canvas_json={}
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
            agreed_total=None,
        )

    def test_order_upload_rejects_16mb(self):
        self.client.force_login(self.customer)
        big = SimpleUploadedFile(
            "big.png",
            b"0" * (16 * 1024 * 1024),
            content_type="image/png",
        )
        resp = self.client.post(
            reverse("order_detail", kwargs={"order_id": self.order.order_id}),
            {
                "channel": self.channel.pk,
                "amount_claimed": "100.00",
                "proof_file": big,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "15 MB")
        self.assertFalse(Payment.objects.filter(order=self.order).exists())

    def test_submit_accepts_valid_png_and_stores_pending(self):
        self.client.force_login(self.customer)
        design = Design.objects.create(
            owner=self.customer, title="Submit proof", canvas_json={"version": 1}
        )
        resp = self.client.post(
            reverse("design_submit", args=[design.pk]),
            {
                "channel": self.channel.pk,
                "amount_claimed": "100.00",
                "canvas_json": '{"version":1,"objects":[]}',
                "window_started_at": timezone.now().isoformat(),
                "proof_file": SimpleUploadedFile(
                    "ok.png", _make_png_bytes(), content_type="image/png"
                ),
                "preview_image": SimpleUploadedFile(
                    "preview_front.png",
                    _make_png_bytes((48, 48)),
                    content_type="image/png",
                ),
                "preview_back_image": SimpleUploadedFile(
                    "preview_back.png",
                    _make_png_bytes((48, 48), (50, 50, 60)),
                    content_type="image/png",
                ),
            },
        )
        order = Order.objects.get(design=design)
        self.assertRedirects(
            resp, reverse("order_detail", kwargs={"order_id": order.order_id})
        )
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(order.total_paid, Decimal("0.00"))
