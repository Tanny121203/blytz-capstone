from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import Design
from apps.orders.models import Order

User = get_user_model()


class CustomerOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="other@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.owner,
            title="Owner design",
            canvas_json={},
        )
        self.order = Order.objects.create(
            customer=self.owner,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
        )

    def test_customer_cannot_open_another_customers_design(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(response.status_code, 404)

    def test_customer_cannot_open_another_customers_order(self):
        self.client.force_login(self.other)
        response = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(response.status_code, 404)

    def test_owner_can_open_own_design_and_order(self):
        self.client.force_login(self.owner)
        design_resp = self.client.get(reverse("design_editor", args=[self.design.pk]))
        order_resp = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(design_resp.status_code, 200)
        self.assertEqual(order_resp.status_code, 200)

    def test_design_list_only_shows_own_designs(self):
        Design.objects.create(owner=self.other, title="Other design", canvas_json={})
        self.client.force_login(self.owner)
        response = self.client.get(reverse("design_list"))
        self.assertContains(response, "Owner design")
        self.assertNotContains(response, "Other design")

    def test_order_list_only_shows_own_orders(self):
        other_design = Design.objects.create(
            owner=self.other, title="Other", canvas_json={}
        )
        other_order = Order.objects.create(
            customer=self.other,
            design=other_design,
            status=Order.Status.PRODUCTION,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("order_list"))
        self.assertContains(response, self.order.order_id)
        self.assertNotContains(response, other_order.order_id)


class LandingPageTests(TestCase):
    def test_landing_renders_for_anonymous(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start designing")
        self.assertContains(response, "Strictly no refunds")
        self.assertContains(response, "demo-widget")

    def test_landing_redirects_authenticated_customer(self):
        customer = User.objects.create_user(
            email="landing-auth@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.client.force_login(customer)
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("app_home"))
