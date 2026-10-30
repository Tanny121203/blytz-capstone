"""Stage I.1: one Order per Design under overlapping submits.

SQLite (this project's test backend) does not emit FOR UPDATE. The submit
view takes a writer lock with an UPDATE before re-checking, and
unique_order_per_design rejects a second insert if that lock is bypassed.
"""

from __future__ import annotations

import json
import threading
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from unittest.mock import patch

from apps.designs.models import Design
from apps.orders.models import Order, Payment, PaymentChannel
from apps.sales.models import Lead

User = get_user_model()

SUBMIT_CANVAS = {
    "schema_version": 1,
    "width": 800,
    "height": 800,
    "canvas": {
        "version": "6.6.1",
        "objects": [
            {"type": "rect", "width": 10, "height": 10, "fill": "#111111"}
        ],
    },
    "views": {"back": {"version": "6.6.1", "objects": []}},
}


def _png(name: str) -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (48, 48), color=(40, 40, 40)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def _canvas(fill: str) -> dict:
    payload = json.loads(json.dumps(SUBMIT_CANVAS))
    payload["canvas"]["objects"][0]["fill"] = fill
    return payload


class OrderDesignUniquenessTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="uniq@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Uniq GCash",
            account_name="Blytz",
            account_number="09170002222",
            is_active=True,
        )
        stored = _canvas("#010101")
        stored["kept"] = True
        self.design = Design.objects.create(
            owner=self.customer,
            title="Unique design",
            canvas_json=stored,
        )

    def test_sqlite_select_for_update_does_not_emit_for_update(self):
        self.assertEqual(connection.vendor, "sqlite")
        self.assertFalse(connection.features.has_select_for_update)
        sql = str(Design.objects.select_for_update().filter(pk=self.design.pk).query)
        self.assertNotIn("FOR UPDATE", sql.upper())

    def test_second_order_for_same_design_raises_integrity_error(self):
        Order.objects.create(
            customer=self.customer,
            design=self.design,
            status=Order.Status.JOB_REQUEST,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(
                    customer=self.customer,
                    design=self.design,
                    status=Order.Status.JOB_REQUEST,
                )
        self.assertEqual(Order.objects.filter(design=self.design).count(), 1)

    def test_integrity_error_response_hides_database_text(self):
        def raise_integrity(*args, **kwargs):
            raise IntegrityError(
                "UNIQUE constraint failed: orders_order.design_id"
            )

        started = timezone.now().isoformat()
        self.client.force_login(self.customer)
        with patch(
            "apps.designs.views.Order.objects.create",
            side_effect=raise_integrity,
        ):
            response = self.client.post(
                reverse("design_submit", args=[self.design.pk]),
                {
                    "channel": self.channel.pk,
                    "amount_claimed": "500.00",
                    "canvas_json": json.dumps(_canvas("#111111")),
                    "window_started_at": started,
                    "proof_file": _png("proof.png"),
                    "preview_image": _png("preview_front.png"),
                    "preview_back_image": _png("preview_back.png"),
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                HTTP_ACCEPT="application/json",
            )
        self.assertEqual(response.status_code, 400)
        body = response.content.decode()
        self.assertNotIn("UNIQUE", body)
        self.assertNotIn("orders_order", body)
        self.assertNotIn("sqlite", body.lower())
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("design", data["errors"])
        self.assertFalse(Order.objects.filter(design=self.design).exists())
        self.design.refresh_from_db()
        self.assertTrue(self.design.canvas_json.get("kept"))
        self.assertEqual(
            self.design.canvas_json["canvas"]["objects"][0]["fill"], "#010101"
        )


class ConcurrentDesignSubmitTests(TransactionTestCase):
    """Two connections pass the in-transaction re-check, then one insert wins."""

    def setUp(self):
        self.customer = User.objects.create_user(
            email="race@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Race GCash",
            account_name="Blytz",
            account_number="09170003333",
            is_active=True,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Race design",
            canvas_json=_canvas("#000000"),
            garment_template="tee",
            garment_color="white",
        )

    @override_settings(
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies"
    )
    def test_overlapping_submits_persist_one_order(self):
        """Two request threads, two connections, released together."""
        start = threading.Barrier(2)
        results = []

        # Log in before the race so session setup is not part of the overlap.
        clients = []
        for _ in range(2):
            client = Client()
            client.force_login(self.customer)
            clients.append(client)

        def worker(client: Client, fill: str):
            from django.db import connections

            connections.close_all()
            try:
                start.wait(timeout=20)
                response = client.post(
                    reverse("design_submit", args=[self.design.pk]),
                    {
                        "channel": self.channel.pk,
                        "amount_claimed": "500.00",
                        "canvas_json": json.dumps(_canvas(fill)),
                        "window_started_at": timezone.now().isoformat(),
                        "garment_template": "tee",
                        "garment_color": "white",
                        "proof_file": _png(f"proof-{fill}.png"),
                        "preview_image": _png(f"front-{fill}.png"),
                        "preview_back_image": _png(f"back-{fill}.png"),
                    },
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                    HTTP_ACCEPT="application/json",
                )
                results.append(
                    {
                        "status": response.status_code,
                        "body": response.content.decode(),
                    }
                )
            except Exception as exc:
                results.append({"error": f"{type(exc).__name__}: {exc}"})
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=worker, args=(clients[0], "#111111")),
            threading.Thread(target=worker, args=(clients[1], "#222222")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "submit thread did not finish")

        errors = [row for row in results if "error" in row]
        self.assertEqual(errors, [], results)
        self.assertEqual(len(results), 2, results)

        statuses = sorted(row["status"] for row in results)
        self.assertEqual(statuses, [200, 400], results)
        for row in results:
            lowered = row["body"].lower()
            self.assertNotIn("unique constraint", lowered)
            self.assertNotIn("orders_order", lowered)
            self.assertNotIn("database is locked", lowered)
            self.assertNotIn("sqlite", lowered)

        success = next(row for row in results if row["status"] == 200)
        failure = next(row for row in results if row["status"] == 400)
        success_data = json.loads(success["body"])
        failure_data = json.loads(failure["body"])
        self.assertTrue(success_data["ok"])
        self.assertTrue(success_data["redirect"])
        self.assertFalse(failure_data["ok"])
        self.assertIn("design", failure_data["errors"])
        # SQLite can report the lock before the winner commits, so the losing
        # response is either "already submitted" or a retry with no SQL text.
        failure_text = " ".join(failure_data["errors"]["design"]).lower()
        self.assertTrue(
            "already submitted" in failure_text
            or "please try again" in failure_text,
            failure_text,
        )

        orders = list(Order.objects.filter(design=self.design))
        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(Lead.objects.filter(order=order).count(), 1)
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json, order.canvas_json_snapshot)
        self.assertIn(
            order.canvas_json_snapshot["canvas"]["objects"][0]["fill"],
            {"#111111", "#222222"},
        )
        self.assertTrue(self.design.is_submitted)

        follow = clients[0].post(
            reverse("design_submit", args=[self.design.pk]),
            {
                "channel": self.channel.pk,
                "amount_claimed": "500.00",
                "canvas_json": json.dumps(_canvas("#333333")),
                "window_started_at": timezone.now().isoformat(),
                "garment_template": "tee",
                "garment_color": "white",
                "proof_file": _png("proof-follow.png"),
                "preview_image": _png("front-follow.png"),
                "preview_back_image": _png("back-follow.png"),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(follow.status_code, 400)
        self.assertIn("already submitted", follow.content.decode().lower())
        self.assertEqual(Order.objects.filter(design=self.design).count(), 1)
        self.design.refresh_from_db()
        self.assertNotEqual(
            self.design.canvas_json["canvas"]["objects"][0]["fill"], "#333333"
        )
