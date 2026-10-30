from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.designs.models import ActivityLog, Design
from apps.orders.models import Order, Payment, PaymentChannel
from apps.sales.models import Lead

User = get_user_model()


class UserAccountingPermissionTests(TestCase):
    def test_can_edit_accounting_page_helper(self):
        admin = User.objects.create_user(
            email="admin@test.com",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
            can_edit_accounting=False,
        )
        staff_flagged = User.objects.create_user(
            email="staff-edit@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
            can_edit_accounting=True,
        )
        staff_plain = User.objects.create_user(
            email="staff@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
            can_edit_accounting=False,
        )
        customer = User.objects.create_user(
            email="customer@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )

        self.assertTrue(admin.can_edit_accounting_page())
        self.assertTrue(staff_flagged.can_edit_accounting_page())
        self.assertFalse(staff_plain.can_edit_accounting_page())
        self.assertFalse(customer.can_edit_accounting_page())


class OrderModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="buyer@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Test Tee",
            garment_template="tee",
            garment_color="black",
            canvas_json={"objects": []},
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Test GCash",
            account_name="Blytz",
            account_number="09170000000",
            is_active=True,
        )

    def test_order_id_auto_generated(self):
        order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
        )
        self.assertTrue(order.order_id.startswith("BLY-"))
        self.assertEqual(len(order.order_id), 10)
        self.assertEqual(order.order_id, "BLY-000001")

        design2 = Design.objects.create(
            owner=self.customer,
            title="Second",
            canvas_json={},
        )
        order2 = Order.objects.create(
            customer=self.customer,
            design=design2,
            status=Order.Status.JOB_REQUEST,
        )
        self.assertEqual(order2.order_id, "BLY-000002")

    def test_total_paid_balance_and_payment_status(self):
        order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            agreed_total=Decimal("1000.00"),
            status=Order.Status.PRODUCTION,
        )
        self.assertEqual(order.total_paid, Decimal("0.00"))
        self.assertEqual(order.balance, Decimal("1000.00"))
        self.assertEqual(order.payment_status, Order.OUTSTANDING)

        Payment.objects.create(
            order=order,
            channel=self.channel,
            amount_claimed=Decimal("400.00"),
            status=Payment.Status.ACCEPTED,
        )
        self.assertEqual(order.total_paid, Decimal("400.00"))
        self.assertEqual(order.balance, Decimal("600.00"))
        self.assertEqual(order.payment_status, Order.OUTSTANDING)

        Payment.objects.create(
            order=order,
            channel=self.channel,
            amount_claimed=Decimal("600.00"),
            status=Payment.Status.ACCEPTED,
        )
        self.assertEqual(order.total_paid, Decimal("1000.00"))
        self.assertEqual(order.balance, Decimal("0.00"))
        self.assertEqual(order.payment_status, Order.FULLY_PAID)

    def test_payment_status_without_agreed_total(self):
        order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            agreed_total=None,
            status=Order.Status.JOB_REQUEST,
        )
        Payment.objects.create(
            order=order,
            channel=self.channel,
            amount_claimed=Decimal("100.00"),
            status=Payment.Status.ACCEPTED,
        )
        self.assertIsNone(order.balance)
        self.assertEqual(order.payment_status, Order.OUTSTANDING)

    def test_design_submitted_via_order(self):
        self.assertFalse(self.design.is_submitted)
        Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
        )
        self.assertTrue(self.design.is_submitted)

    def test_lead_and_activity_log(self):
        order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
        )
        lead = Lead.objects.create(
            customer=self.customer,
            order=order,
            stage=Lead.Stage.NEW_LEAD,
        )
        log = ActivityLog.objects.create(
            customer=self.customer,
            design=self.design,
            order=order,
            kind=ActivityLog.Kind.DESIGN_SUBMITTED,
        )
        self.assertEqual(lead.stage, Lead.Stage.NEW_LEAD)
        self.assertEqual(log.kind, ActivityLog.Kind.DESIGN_SUBMITTED)
        self.assertEqual(str(order), "BLY-000001")
