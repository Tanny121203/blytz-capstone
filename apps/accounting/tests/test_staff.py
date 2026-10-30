from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import ActivityLog, Design
from apps.orders.models import Order, Payment, PaymentChannel
from apps.sales.models import Lead

User = get_user_model()


class StaffPipelineTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.staff_edit = User.objects.create_user(
            email="staff-edit@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
            can_edit_accounting=True,
        )
        self.staff_view = User.objects.create_user(
            email="staff-view@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
            can_edit_accounting=False,
        )
        self.customer = User.objects.create_user(
            email="cust@test.com",
            password="x",
            role=User.Role.CUSTOMER,
            first_name="Casey",
        )
        self.design = Design.objects.create(
            owner=self.customer, title="Pipe design", canvas_json={}
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
            agreed_total=Decimal("1000.00"),
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Staff Test GCash",
            account_name="Blytz",
            account_number="09170009999",
            is_active=True,
        )
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("100.00"),
            status=Payment.Status.ACCEPTED,
        )
        self.lead = Lead.objects.create(
            customer=self.customer,
            order=self.order,
            stage=Lead.Stage.NEW_LEAD,
        )

    def test_customer_forbidden_on_staff_areas(self):
        self.client.force_login(self.customer)
        for name, kwargs in [
            ("jobs_pipeline", {}),
            ("staff_order_detail", {"order_id": self.order.order_id}),
            ("accounting_list", {}),
            ("accounting_detail", {"order_id": self.order.order_id}),
            ("sales_pipeline", {}),
            ("lead_detail", {"lead_id": self.lead.pk}),
        ]:
            resp = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(resp.status_code, 403, msg=name)

    def test_admin_can_edit_accounting(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("accounting_detail", kwargs={"order_id": self.order.order_id}),
            {"action": "set_total", "agreed_total": "1500.00"},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.agreed_total, Decimal("1500.00"))
        self.assertEqual(self.order.accounting_edited_by_id, self.admin.pk)
        self.assertIsNotNone(self.order.accounting_edited_at)

    def test_staff_with_permission_can_edit_accounting(self):
        self.client.force_login(self.staff_edit)
        resp = self.client.post(
            reverse("accounting_detail", kwargs={"order_id": self.order.order_id}),
            {
                "action": "add_payment",
                "amount_claimed": "250.00",
                "note": "Manual top-up",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        # Existing accepted 100 + new manual 250 (auto-accepted)
        self.assertEqual(self.order.total_paid, Decimal("350.00"))
        self.assertEqual(self.order.accounting_edited_by_id, self.staff_edit.pk)
        manual = Payment.objects.filter(
            order=self.order, is_manual_adjustment=True
        ).get()
        self.assertEqual(manual.status, Payment.Status.ACCEPTED)

    def test_staff_without_permission_gets_403_on_post(self):
        self.client.force_login(self.staff_view)
        get_resp = self.client.get(
            reverse("accounting_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertNotContains(get_resp, "Save agreed total")
        post_resp = self.client.post(
            reverse("accounting_detail", kwargs={"order_id": self.order.order_id}),
            {"action": "set_total", "agreed_total": "999.00"},
        )
        self.assertEqual(post_resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.agreed_total, Decimal("1000.00"))

    def test_advance_phase_one_step_and_logs(self):
        self.client.force_login(self.staff_view)
        resp = self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_EDIT)
        self.assertTrue(
            ActivityLog.objects.filter(
                order=self.order, kind=ActivityLog.Kind.PHASE_MOVED
            ).exists()
        )

    def test_jobs_pipeline_search(self):
        self.client.force_login(self.staff_view)
        resp = self.client.get(reverse("jobs_pipeline"), {"q": self.order.order_id})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.order.order_id)

    def test_sales_incomplete_tab_excludes_submitted(self):
        Design.objects.create(owner=self.customer, title="Draft only", canvas_json={})
        self.client.force_login(self.staff_view)
        resp = self.client.get(reverse("sales_pipeline"), {"tab": "incomplete"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Draft only")
        self.assertNotContains(resp, "Pipe design")
