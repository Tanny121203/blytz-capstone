"""Staff overview charts: permissions, aggregates, empty states."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.dashboard import (
    new_orders_per_day_chart,
    orders_by_phase_chart,
    payments_awaiting_review_count,
)
from apps.designs.models import Design
from apps.orders.models import Order, Payment, PaymentChannel

User = get_user_model()


class StaffOverviewChartTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-charts@test.com",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            email="staff-charts@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email="cust-charts@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )

    def test_staff_and_admin_get_200_with_chart_markup(self):
        for user in (self.staff, self.admin):
            self.client.force_login(user)
            resp = self.client.get(reverse("staff_home"))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Orders by phase")
            self.assertContains(resp, "New orders (30 days)")
            self.assertContains(resp, "Payments awaiting review")
            self.assertContains(resp, 'id="chart-orders-by-phase"')
            self.assertContains(resp, 'id="chart-orders-per-day"')
            self.assertContains(resp, "vendor/chartjs/chart.umd.min.js")
            self.assertContains(resp, "staff_charts.js")
            self.assertContains(resp, "View data table")
            self.assertContains(
                resp, reverse("jobs_pipeline") + "?pending_review=1"
            )

    def test_customer_gets_403(self):
        self.client.force_login(self.customer)
        resp = self.client.get(reverse("staff_home"))
        self.assertEqual(resp.status_code, 403)

    def test_empty_database_renders_empty_states(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("staff_home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No data yet")
        self.assertEqual(resp.context["phase_chart"]["empty"], True)
        self.assertEqual(resp.context["orders_per_day_chart"]["empty"], True)
        self.assertEqual(resp.context["stat_pending_review"], 0)

    def test_phase_and_pending_aggregates(self):
        design_a = Design.objects.create(
            owner=self.customer, title="A", canvas_json={}
        )
        design_b = Design.objects.create(
            owner=self.customer, title="B", canvas_json={}
        )
        Order.objects.create(
            customer=self.customer,
            design=design_a,
            status=Order.Status.JOB_REQUEST,
        )
        Order.objects.create(
            customer=self.customer,
            design=design_b,
            status=Order.Status.PRODUCTION,
        )
        channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="0917",
            is_active=True,
        )
        order_b = Order.objects.get(design=design_b)
        Payment.objects.create(
            order=order_b,
            channel=channel,
            amount_claimed=Decimal("100.00"),
            status=Payment.Status.PENDING,
        )
        Payment.objects.create(
            order=order_b,
            channel=channel,
            amount_claimed=Decimal("50.00"),
            status=Payment.Status.REJECTED,
        )

        chart = orders_by_phase_chart()
        self.assertFalse(chart["empty"])
        self.assertEqual(chart["values"][0], 1)  # job request
        self.assertEqual(chart["values"][2], 1)  # production
        self.assertEqual(payments_awaiting_review_count(), 1)

        self.client.force_login(self.staff)
        resp = self.client.get(reverse("staff_home"))
        self.assertEqual(resp.context["stat_pending_review"], 1)

    def test_new_orders_per_day_uses_created_at(self):
        design = Design.objects.create(
            owner=self.customer, title="Dated", canvas_json={}
        )
        order = Order.objects.create(
            customer=self.customer,
            design=design,
            status=Order.Status.JOB_REQUEST,
        )
        day = timezone.now() - timedelta(days=3)
        Order.objects.filter(pk=order.pk).update(created_at=day)
        chart = new_orders_per_day_chart(days=30)
        self.assertFalse(chart["empty"])
        self.assertEqual(sum(chart["values"]), 1)

    def test_pending_review_jobs_filter(self):
        design = Design.objects.create(
            owner=self.customer, title="Pending pay", canvas_json={}
        )
        order = Order.objects.create(
            customer=self.customer,
            design=design,
            status=Order.Status.JOB_REQUEST,
        )
        other_design = Design.objects.create(
            owner=self.customer, title="No pending", canvas_json={}
        )
        other = Order.objects.create(
            customer=self.customer,
            design=other_design,
            status=Order.Status.JOB_REQUEST,
        )
        channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.MAYA,
            display_name="Maya",
            account_name="Blytz",
            account_number="0918",
            is_active=True,
        )
        Payment.objects.create(
            order=order,
            channel=channel,
            amount_claimed=Decimal("10.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("jobs_pipeline"), {"pending_review": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, order.order_id)
        self.assertNotContains(resp, other.order_id)
        self.assertContains(resp, "payment awaiting review")
