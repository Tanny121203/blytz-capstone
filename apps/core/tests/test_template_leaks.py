from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import Design
from apps.orders.models import Order, PaymentChannel
from apps.sales.models import Lead

User = get_user_model()

LEAK_MARKERS = ("{#", "{%", "{{")


class TemplateLeakTests(TestCase):
    """Fail if rendered HTML still contains raw template syntax."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.customer = User.objects.get(email="customer1@blytz.demo")
        cls.staff = User.objects.get(email="staff@blytz.demo")
        cls.admin = User.objects.get(email="admin@blytz.demo")
        cls.design = Design.objects.filter(owner=cls.customer).first()
        cls.order = Order.objects.filter(customer=cls.customer).first()
        cls.channel = PaymentChannel.objects.filter(is_active=True).first()
        cls.lead = Lead.objects.first()
        cls.staff_target = User.objects.get(email="staff.accounting@blytz.demo")

    def _urls_for_role(self, role: str):
        urls = [
            reverse("home"),
            reverse("account_login"),
            reverse("account_signup"),
        ]
        if role == "customer":
            urls += [
                reverse("app_home"),
                reverse("design_list"),
                reverse("account_profile"),
                reverse("order_list"),
            ]
            if self.design:
                urls += [
                    reverse("design_detail", args=[self.design.pk]),
                    reverse("design_editor", args=[self.design.pk]),
                ]
            if self.order:
                urls.append(reverse("order_detail", args=[self.order.order_id]))
            # Admin/staff pages (expect 403 bodies still clean)
            urls += [
                reverse("staff_home"),
                reverse("jobs_pipeline"),
                reverse("accounting_list"),
                reverse("sales_pipeline"),
                reverse("payment_channel_list"),
                reverse("user_manage_list"),
            ]
        elif role == "staff":
            urls += [
                reverse("staff_home"),
                reverse("jobs_pipeline"),
                reverse("accounting_list"),
                reverse("sales_pipeline"),
                reverse("account_profile"),
                reverse("payment_channel_list"),
                reverse("user_manage_list"),
                reverse("staff_admin_only"),
            ]
            if self.order:
                urls += [
                    reverse("staff_order_detail", args=[self.order.order_id]),
                    reverse("accounting_detail", args=[self.order.order_id]),
                ]
            if self.lead:
                urls.append(reverse("lead_detail", args=[self.lead.pk]))
        else:  # admin
            urls += [
                reverse("staff_home"),
                reverse("jobs_pipeline"),
                reverse("accounting_list"),
                reverse("sales_pipeline"),
                reverse("staff_admin_only"),
                reverse("payment_channel_list"),
                reverse("payment_channel_create"),
                reverse("user_manage_list"),
                reverse("user_create_staff"),
                reverse("user_edit", args=[self.staff_target.pk]),
            ]
            if self.channel:
                urls.append(reverse("payment_channel_edit", args=[self.channel.pk]))
            if self.order:
                urls += [
                    reverse("staff_order_detail", args=[self.order.order_id]),
                    reverse("accounting_detail", args=[self.order.order_id]),
                ]
            if self.lead:
                urls.append(reverse("lead_detail", args=[self.lead.pk]))
        return urls

    def _assert_no_leaks(self, response, url, role):
        body = response.content.decode("utf-8", errors="replace")
        for marker in LEAK_MARKERS:
            self.assertNotIn(
                marker,
                body,
                msg=f"Template leak {marker!r} on {url} as {role} (status {response.status_code})",
            )

    def _check_urls(self, role, user):
        self.client.force_login(user)
        for url in self._urls_for_role(role):
            response = self.client.get(url, follow=False)
            if response.status_code in (301, 302):
                # Follow once for login/home redirects; still inspect final HTML
                response = self.client.get(url, follow=True)
            self.assertIn(
                response.status_code,
                (200, 403),
                msg=f"{url} as {role} -> {response.status_code}",
            )
            self._assert_no_leaks(response, url, role)

    def test_no_template_leaks_as_customer(self):
        self._check_urls("customer", self.customer)

    def test_no_template_leaks_as_staff(self):
        self._check_urls("staff", self.staff)

    def test_no_template_leaks_as_admin(self):
        self._check_urls("admin", self.admin)
