from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from PIL import Image

from apps.designs.models import Design
from apps.orders.models import Order, Payment, PaymentChannel

User = get_user_model()


def _png(name="proof.png", size=(32, 32)):
    buffer = BytesIO()
    Image.new("RGB", size, color=(200, 162, 39)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class PaymentClaimModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="buyer@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Claim Tee",
            canvas_json={},
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="09171111111",
            is_active=True,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            agreed_total=Decimal("1000.00"),
            status=Order.Status.JOB_REQUEST,
        )

    def test_only_accepted_payments_count(self):
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("300.00"),
            status=Payment.Status.REJECTED,
        )
        self.assertEqual(self.order.total_paid, Decimal("0.00"))
        self.assertFalse(self.order.has_accepted_payment)
        self.assertIsNotNone(self.order.pending_payment)

        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("1000.00"),
            status=Payment.Status.ACCEPTED,
        )
        self.assertEqual(self.order.total_paid, Decimal("1000.00"))
        self.assertEqual(self.order.payment_status, Order.FULLY_PAID)
        self.assertTrue(self.order.has_accepted_payment)

    def test_reviewed_payments_are_final(self):
        payment = Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("100.00"),
            status=Payment.Status.ACCEPTED,
        )
        staff = User.objects.create_user(
            email="staff@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
        )
        with self.assertRaises(ValueError):
            payment.accept(staff)
        with self.assertRaises(ValueError):
            payment.reject(staff, "nope")


class PaymentReviewViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            email="staff@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
            can_edit_accounting=False,
        )
        self.staff_edit = User.objects.create_user(
            email="staff-edit@test.com",
            password="x",
            role=User.Role.STAFF,
            is_staff=True,
            can_edit_accounting=True,
        )
        self.customer = User.objects.create_user(
            email="cust@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer, title="Review design", canvas_json={}
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="09172222222",
            is_active=True,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
            agreed_total=Decimal("1000.00"),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("500.00"),
            proof_file=_png(),
            status=Payment.Status.PENDING,
        )

    def test_gate_blocks_advance_without_accepted_payment(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.JOB_REQUEST)

        detail = self.client.get(
            reverse("staff_order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertContains(detail, "accepted payment")
        self.assertContains(detail, "disabled")

    def test_gate_allows_advance_with_accepted_payment(self):
        self.payment.accept(self.staff)
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("advance_order_phase", kwargs={"order_id": self.order.order_id})
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_EDIT)

    def test_any_staff_can_review_payment(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse(
                "review_payment",
                kwargs={
                    "order_id": self.order.order_id,
                    "payment_id": self.payment.pk,
                },
            ),
            {"action": "accept"},
        )
        self.assertEqual(resp.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.ACCEPTED)
        self.assertEqual(self.payment.reviewed_by_id, self.staff.pk)

    def test_staff_without_accounting_cannot_edit_accounting(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("accounting_detail", kwargs={"order_id": self.order.order_id}),
            {"action": "set_total", "agreed_total": "50.00"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_customer_gets_403_on_review(self):
        self.client.force_login(self.customer)
        resp = self.client.post(
            reverse(
                "review_payment",
                kwargs={
                    "order_id": self.order.order_id,
                    "payment_id": self.payment.pk,
                },
            ),
            {"action": "accept"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_manual_adjustment_auto_accepted(self):
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
        manual = Payment.objects.filter(
            order=self.order, is_manual_adjustment=True
        ).get()
        self.assertEqual(manual.status, Payment.Status.ACCEPTED)
        self.assertEqual(manual.reviewed_by_id, self.staff_edit.pk)
        self.assertEqual(self.order.total_paid, Decimal("250.00"))

    def test_reject_with_reason(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse(
                "review_payment",
                kwargs={
                    "order_id": self.order.order_id,
                    "payment_id": self.payment.pk,
                },
            ),
            {"action": "reject", "rejection_reason": "Blurry screenshot"},
        )
        self.assertEqual(resp.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.REJECTED)
        self.assertEqual(self.payment.rejection_reason, "Blurry screenshot")
        self.assertEqual(self.order.total_paid, Decimal("0.00"))

    def test_pipeline_and_accounting_show_pending_marker(self):
        self.client.force_login(self.staff)
        jobs = self.client.get(reverse("jobs_pipeline"))
        self.assertContains(jobs, "Payment awaiting review")
        accounting = self.client.get(reverse("accounting_list"))
        self.assertContains(accounting, "Payment awaiting review")


class CustomerPaymentUploadTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="buyer@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="other@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz Clothing",
            account_number="09173333333",
            is_active=True,
        )
        self.design = Design.objects.create(
            owner=self.customer, title="Upload design", canvas_json={}
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.COMPLETED,
            agreed_total=Decimal("1000.00"),
        )
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("400.00"),
            status=Payment.Status.ACCEPTED,
        )

    def _upload(self, *, user=None, order=None, amount="200.00", proof=None):
        user = user or self.customer
        order = order or self.order
        self.client.force_login(user)
        return self.client.post(
            reverse("order_detail", kwargs={"order_id": order.order_id}),
            {
                "channel": self.channel.pk,
                "amount_claimed": amount,
                "proof_file": proof if proof is not None else _png(),
            },
        )

    def test_upload_allowed_on_completed_with_balance(self):
        resp = self._upload()
        self.assertEqual(resp.status_code, 302)
        pending = Payment.objects.filter(
            order=self.order, status=Payment.Status.PENDING
        )
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.get().amount_claimed, Decimal("200.00"))

    def test_upload_allowed_when_no_agreed_total(self):
        self.order.agreed_total = None
        self.order.save(update_fields=["agreed_total"])
        Payment.objects.filter(order=self.order).delete()
        resp = self._upload(amount="150.00")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Payment.objects.filter(
                order=self.order, status=Payment.Status.PENDING
            ).exists()
        )

    def test_second_pending_blocked(self):
        self._upload()
        resp = self._upload(amount="50.00")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(
            Payment.objects.filter(
                order=self.order, status=Payment.Status.PENDING
            ).count(),
            1,
        )
        detail = self.client.get(
            reverse("order_detail", kwargs={"order_id": self.order.order_id})
        )
        self.assertContains(detail, "Payment awaiting staff review")

    def test_paid_order_blocked(self):
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("600.00"),
            status=Payment.Status.ACCEPTED,
        )
        self.assertEqual(self.order.payment_status, Order.FULLY_PAID)
        resp = self._upload()
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(
            Payment.objects.filter(
                order=self.order, status=Payment.Status.PENDING
            ).exists()
        )

    def test_other_customer_forbidden(self):
        resp = self._upload(user=self.other)
        self.assertEqual(resp.status_code, 404)


class ConcurrentPendingPaymentTests(TransactionTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="race@test.com",
            password="x",
            role=User.Role.CUSTOMER,
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="GCash",
            account_name="Blytz",
            account_number="09174444444",
            is_active=True,
        )
        self.design = Design.objects.create(
            owner=self.customer, title="Race design", canvas_json={}
        )
        self.order = Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.PENDING_EDIT,
            agreed_total=Decimal("800.00"),
        )

    def test_concurrent_requests_blocked(self):
        """Race-safe: unique pending constraint + select_for_update create path."""
        from django.db import IntegrityError, transaction

        # Partial unique index: only one pending payment per order.
        Payment.objects.create(
            order=self.order,
            channel=self.channel,
            amount_claimed=Decimal("10.00"),
            status=Payment.Status.PENDING,
        )
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                order=self.order,
                channel=self.channel,
                amount_claimed=Decimal("20.00"),
                status=Payment.Status.PENDING,
            )
        Payment.objects.filter(order=self.order).delete()

        # Same checks the view runs under select_for_update (two tabs / double-click).
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=self.order.pk)
            self.assertIsNone(locked.pending_payment)
            Payment.objects.create(
                order=locked,
                channel=self.channel,
                amount_claimed=Decimal("100.00"),
                status=Payment.Status.PENDING,
            )

        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=self.order.pk)
            self.assertIsNotNone(locked.pending_payment)
            with self.assertRaises(IntegrityError):
                Payment.objects.create(
                    order=locked,
                    channel=self.channel,
                    amount_claimed=Decimal("200.00"),
                    status=Payment.Status.PENDING,
                )

        self.assertEqual(
            Payment.objects.filter(
                order=self.order, status=Payment.Status.PENDING
            ).count(),
            1,
        )
