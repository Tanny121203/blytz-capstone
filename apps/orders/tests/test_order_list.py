"""Stage J: customer submission history (/app/orders/)."""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.designs.garment_choices import format_garment_display
from apps.designs.models import Design
from apps.orders.customer_display import (
    ORDERS_PER_PAGE,
    customer_order_status_label,
)
from apps.orders.models import Order

User = get_user_model()


def _png(name="preview.png"):
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color=(40, 40, 40)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class CustomerOrderStatusLabelTests(TestCase):
    def test_known_statuses_use_display_labels(self):
        self.assertEqual(
            customer_order_status_label(Order.Status.JOB_REQUEST), "Job Request"
        )
        self.assertEqual(
            customer_order_status_label(Order.Status.COMPLETED), "Completed"
        )

    def test_unknown_status_is_not_falsely_positive(self):
        label = customer_order_status_label("not_a_real_phase")
        self.assertIn("Unknown status", label)
        self.assertIn("not_a_real_phase", label)
        self.assertNotEqual(label, "Completed")
        self.assertNotEqual(label, "Fully Paid")
        self.assertNotIn("Approved", label)


class CustomerOrderListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="hist-owner@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="hist-other@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.owner,
            title="Sunset Tee",
            garment_template="tee",
            garment_color="navy",
            canvas_json={},
        )
        self.order = Order.objects.create(
            customer=self.owner,
            design=self.design,
            status=Order.Status.PENDING_EDIT,
            preview_image=_png("front.png"),
        )
        Order.objects.filter(pk=self.order.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.order.refresh_from_db()

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse("order_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_owner_sees_own_submission_fields(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunset Tee")
        self.assertContains(response, self.order.order_id)
        self.assertContains(response, "Pending Edit")
        self.assertContains(response, format_garment_display("tee", "navy"))
        self.assertContains(response, self.order.created_at.strftime("%Y-%m-%d"))
        self.assertContains(response, reverse("order_detail", args=[self.order.order_id]))
        # Thumbnail from existing order preview.
        self.assertContains(response, self.order.preview_image.url)
        # Draft copy is not listed as an order.
        self.assertContains(response, "never submitted")

    def test_other_customers_orders_do_not_appear(self):
        other_design = Design.objects.create(
            owner=self.other, title="Secret Other Design", canvas_json={}
        )
        other_order = Order.objects.create(
            customer=self.other,
            design=other_design,
            status=Order.Status.PRODUCTION,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertContains(response, "Sunset Tee")
        self.assertContains(response, self.order.order_id)
        self.assertNotContains(response, "Secret Other Design")
        self.assertNotContains(response, other_order.order_id)

    def test_draft_without_order_is_not_listed(self):
        Design.objects.create(
            owner=self.owner,
            title="Unsent Draft Only",
            canvas_json={},
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertContains(response, "Sunset Tee")
        self.assertNotContains(response, "Unsent Draft Only")

    def test_empty_history_offers_designs_next_step(self):
        empty_user = User.objects.create_user(
            email="hist-empty@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.client.force_login(empty_user)
        response = self.client.get(reverse("order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No submissions yet")
        self.assertContains(response, "Go to designs")
        self.assertContains(response, "/app/designs/")

    def test_missing_preview_does_not_break_page(self):
        no_preview_design = Design.objects.create(
            owner=self.owner,
            title="No Preview Design",
            garment_template="hoodie",
            garment_color="black",
            canvas_json={},
        )
        Order.objects.create(
            customer=self.owner,
            design=no_preview_design,
            status=Order.Status.JOB_REQUEST,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Preview Design")
        self.assertContains(response, "No preview")

    def test_unknown_status_renders_safe_fallback(self):
        Order.objects.filter(pk=self.order.pk).update(status="mystery_phase")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unknown status (mystery_phase)")
        self.assertNotContains(response, ">Completed<")
        # Must not treat unknown as the known Completed badge for this order.
        body = response.content.decode()
        self.assertIn("mystery_phase", body)

    def test_status_matches_authoritative_order_status(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PRODUCTION)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertContains(response, "Production")
        self.assertNotContains(response, "Pending Edit")

    def test_pagination_splits_submissions(self):
        # Existing setUp order + enough extras to exceed one page.
        for i in range(ORDERS_PER_PAGE):
            design = Design.objects.create(
                owner=self.owner,
                title=f"Paged Design {i:02d}",
                canvas_json={},
            )
            Order.objects.create(
                customer=self.owner,
                design=design,
                status=Order.Status.JOB_REQUEST,
            )
        self.client.force_login(self.owner)
        page1 = self.client.get(reverse("order_list"))
        self.assertEqual(page1.status_code, 200)
        self.assertTrue(page1.context["page_obj"].has_next())
        self.assertEqual(len(page1.context["submissions"]), ORDERS_PER_PAGE)
        self.assertContains(page1, "Next")

        page2 = self.client.get(reverse("order_list"), {"page": "2"})
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(page2.context["page_obj"].number, 2)
        self.assertEqual(len(page2.context["submissions"]), 1)
        self.assertContains(page2, "Previous")

    def test_detail_link_stays_owner_only(self):
        self.client.force_login(self.other)
        response = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(response.status_code, 404)
