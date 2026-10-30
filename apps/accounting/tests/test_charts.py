"""Accounting charts: permissions, accepted-only aggregates, empty states."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounting.charts import (
    collections_over_time_chart,
    collected_vs_outstanding_chart,
    payments_by_channel_chart,
)
from apps.designs.models import Design
from apps.orders.models import Order, Payment, PaymentChannel

User = get_user_model()


class AccountingChartTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-acct-charts@test.com",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            email="staff-acct-charts@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email="cust-acct-charts@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )

    def test_staff_and_admin_get_200_with_chart_markup(self):
        for user in (self.staff, self.admin):
            self.client.force_login(user)
            resp = self.client.get(reverse("accounting_list"))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Collected vs outstanding")
            self.assertContains(resp, "Collections over time")
            self.assertContains(resp, "Payments by channel")
            self.assertContains(resp, 'id="chart-collected-vs-outstanding"')
            self.assertContains(resp, 'id="chart-collections-over-time"')
            self.assertContains(resp, 'id="chart-payments-by-channel"')
            self.assertContains(resp, "vendor/chartjs/chart.umd.min.js")
            self.assertContains(resp, "View data table")

    def test_customer_gets_403(self):
        self.client.force_login(self.customer)
        resp = self.client.get(reverse("accounting_list"))
        self.assertEqual(resp.status_code, 403)

    def test_empty_database_renders_empty_states(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("accounting_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No data yet")
        self.assertTrue(resp.context["collected_chart"]["empty"])
        self.assertTrue(resp.context["collections_chart"]["empty"])
        self.assertTrue(resp.context["channel_chart"]["empty"])

    def test_aggregates_count_only_accepted_payments(self):
        design = Design.objects.create(
            owner=self.customer, title="Pay mix", canvas_json={}
        )
        order = Order.objects.create(
            customer=self.customer,
            design=design,
            status=Order.Status.JOB_REQUEST,
            agreed_total=Decimal("1000.00"),
        )
        gcash = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="1",
            is_active=True,
        )
        maya = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.MAYA,
            display_name="Maya",
            account_name="Blytz",
            account_number="2",
            is_active=True,
        )
        bank = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.BANK,
            display_name="Bank",
            account_name="Blytz",
            account_number="3",
            is_active=True,
        )
        Payment.objects.create(
            order=order,
            channel=gcash,
            amount_claimed=Decimal("400.00"),
            status=Payment.Status.ACCEPTED,
        )
        Payment.objects.create(
            order=order,
            channel=maya,
            amount_claimed=Decimal("200.00"),
            status=Payment.Status.PENDING,
        )
        Payment.objects.create(
            order=order,
            channel=bank,
            amount_claimed=Decimal("300.00"),
            status=Payment.Status.REJECTED,
        )
        Payment.objects.create(
            order=order,
            channel=maya,
            amount_claimed=Decimal("100.00"),
            status=Payment.Status.ACCEPTED,
        )

        collected = collected_vs_outstanding_chart([order])
        self.assertFalse(collected["empty"])
        self.assertEqual(collected["values"][0], 500.0)  # accepted only
        self.assertEqual(collected["values"][1], 500.0)  # outstanding

        by_channel = payments_by_channel_chart()
        self.assertFalse(by_channel["empty"])
        # labels: GCash, Maya, Bank
        self.assertEqual(by_channel["labels"][:3], ["GCash", "Maya", "Bank"])
        self.assertEqual(by_channel["values"][0], 400.0)
        self.assertEqual(by_channel["values"][1], 100.0)
        self.assertEqual(by_channel["values"][2], 0.0)

        # Backdate accepted payments and ensure line chart uses them
        for payment in Payment.objects.filter(status=Payment.Status.ACCEPTED):
            Payment.objects.filter(pk=payment.pk).update(
                created_at=timezone.now() - timedelta(days=2)
            )
        over_time = collections_over_time_chart(days=30)
        self.assertFalse(over_time["empty"])
        self.assertEqual(sum(over_time["values"]), 500.0)

        self.client.force_login(self.staff)
        resp = self.client.get(reverse("accounting_list"))
        self.assertEqual(resp.context["total_collected"], Decimal("500.00"))
        self.assertEqual(resp.context["collected_chart"]["values"][0], 500.0)
