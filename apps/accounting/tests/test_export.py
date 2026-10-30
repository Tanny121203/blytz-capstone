"""Staff/admin read-only orders CSV export (Stage L)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.designs.models import Design
from apps.orders.models import Order, Payment, PaymentChannel

User = get_user_model()


class AccountingExportCsvTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff-export@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            email="admin-export@test.com",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.customer = User.objects.create_user(
            email="cust-export@test.com",
            password="x",
            role=User.Role.CUSTOMER,
            first_name="Casey",
            last_name="Export",
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Export Tee",
            canvas_json={},
            garment_template="tee",
            garment_color="navy",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
            agreed_total=Decimal("500.00"),
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Export GCash",
            account_name="Blytz",
            account_number="09170001111",
            is_active=True,
        )
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("100.00"),
            status=Payment.Status.PENDING,
        )

    def test_customer_blocked_from_export(self):
        self.client.force_login(self.customer)
        resp = self.client.get(reverse("accounting_export_csv"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_export_csv_headers_and_distinct_statuses(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("accounting_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn("blytz-orders-export.csv", resp["Content-Disposition"])

        body = resp.content.decode("utf-8")
        lines = [line for line in body.splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 2)
        header = lines[0]
        self.assertIn("job_status", header)
        self.assertIn("payment_status", header)
        self.assertNotEqual(
            header.index("job_status"), header.index("payment_status")
        )

        row = lines[1]
        self.assertIn(self.order.order_id, row)
        self.assertIn("Job Request", row)
        self.assertIn("Outstanding Balance", row)
        self.assertIn("T-shirt · Navy", row)
        self.assertIn("yes", row)
        # Job phase label must not be collapsed into payment wording.
        self.assertNotIn("Fully Paid", row)

    def test_admin_can_export(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("accounting_export_csv"))
        self.assertEqual(resp.status_code, 200)

    def test_status_filter_and_empty_result(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("accounting_export_csv"),
            {"status": Order.Status.COMPLETED},
        )
        self.assertEqual(resp.status_code, 200)
        lines = [
            line
            for line in resp.content.decode("utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(lines), 1)
        self.assertIn("order_id", lines[0])

    def test_invalid_status_rejected(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("accounting_export_csv"),
            {"status": "not_a_phase"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_date_rejected(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("accounting_export_csv"),
            {"date_from": "19-10-2026"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_date_range_scopes_rows(self):
        self.client.force_login(self.staff)
        today = timezone.localdate()
        resp = self.client.get(
            reverse("accounting_export_csv"),
            {
                "date_from": today.isoformat(),
                "date_to": today.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn(self.order.order_id, body)

        resp_empty = self.client.get(
            reverse("accounting_export_csv"),
            {
                "date_from": "2000-01-01",
                "date_to": "2000-01-02",
            },
        )
        self.assertEqual(resp_empty.status_code, 200)
        lines = [
            line
            for line in resp_empty.content.decode("utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(lines), 1)

    def test_export_is_read_only(self):
        self.client.force_login(self.staff)
        before_status = self.order.status
        before_canvas = self.design.canvas_json
        before_payments = Payment.objects.filter(order=self.order).count()
        resp = self.client.get(reverse("accounting_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.design.refresh_from_db()
        self.assertEqual(self.order.status, before_status)
        self.assertEqual(self.design.canvas_json, before_canvas)
        self.assertEqual(
            Payment.objects.filter(order=self.order).count(), before_payments
        )

    def test_accounting_list_exposes_export_form(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("accounting_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'action="' + reverse("accounting_export_csv") + '"')
        self.assertContains(resp, "Export CSV")
