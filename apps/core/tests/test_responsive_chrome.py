"""SOURCE-STRING / markup checks for responsive chrome (non-editor + editor)."""

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import Design
from apps.orders.models import Order

User = get_user_model()


class ResponsiveChromeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.customer = User.objects.get(email="customer1@blytz.demo")
        cls.staff = User.objects.get(email="staff@blytz.demo")
        cls.design = Design.objects.filter(owner=cls.customer).first()
        cls.order = Order.objects.filter(customer=cls.customer).first()

    def test_responsive_css_uses_dvh_and_coarse_pointer(self):
        path = finders.find("css/responsive.css")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("100vh", source)
        self.assertIn("100dvh", source)
        self.assertIn("(pointer: coarse)", source)
        self.assertIn("[data-pipeline-panel].is-inactive", source)
        self.assertIn("editor-context-bar", source)
        self.assertIn("touch-action: none", source)
        self.assertIn("payment-upload-sheet", source)
        self.assertIn("safe-area-inset-bottom", source)

    def test_editor_canvas_image_max_edge_is_2000(self):
        path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("IMAGE_MAX_EDGE = 2000", source)
        self.assertIn("IMAGE_EDGE_STEPS = [2000, 1600, 1200, 1000, 800]", source)
        self.assertIn("touchCornerSize = 36", source)
        self.assertIn("function undo", source)
        self.assertIn("wireCanvasGestures", source)
        self.assertIn("prefersSheetTextEdit", source)

    def test_blytz_editor_exposes_undo_redo(self):
        path = finders.find("js/editor_contract.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("undo:", source)
        self.assertIn("redo:", source)
        self.assertIn("canUndo:", source)
        self.assertIn("canRedo:", source)

    def test_jobs_pipeline_renders_phases_once(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("jobs_pipeline"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("pipeline-tabs", html)
        self.assertIn("pipeline-board", html)
        self.assertIn("md:grid-cols-2", html)
        self.assertIn("xl:grid-cols-4", html)
        self.assertIn("md:hidden", html)
        self.assertNotIn("pipeline-mobile", html)
        self.assertNotIn("pipeline-tablet-snap", html)
        self.assertNotIn("pipeline-tablet-grid", html)
        self.assertNotIn("pipeline-desktop", html)
        self.assertNotIn("{#", html)

        for status, label in (
            ("job_request", "Job Request"),
            ("pending_edit", "Pending Edit"),
            ("production", "Production"),
            ("completed", "Completed"),
        ):
            self.assertEqual(
                html.count(f'data-pipeline-panel="{status}"'),
                1,
                msg=f"phase {status} should appear once",
            )
            self.assertEqual(
                html.count(f">{label}</h2>"),
                1,
                msg=f"phase heading {label!r} should appear once",
            )

        for order in Order.objects.all():
            # One card: order_id in the detail href and once as visible mono text.
            self.assertEqual(
                html.count(f"/staff/orders/{order.order_id}/"),
                1,
                msg=f"{order.order_id} card link should appear exactly once",
            )
            self.assertEqual(
                html.count(f">{order.order_id}</p>"),
                1,
                msg=f"{order.order_id} label should appear exactly once",
            )

    def test_staff_order_detail_landscape_two_column_classes(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("staff_order_detail", args=[self.order.order_id])
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("md:landscape:grid-cols-2", html)

    def test_editor_phone_chrome_markup(self):
        self.client.force_login(self.customer)
        resp = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("data-editor-undo", html)
        self.assertIn("data-editor-redo", html)
        self.assertIn("editor-context-bar", html)
        self.assertIn("data-editor-view", html)
        self.assertIn("editor_chrome.js", html)
        self.assertIn('capture="environment"', html)
        self.assertNotIn("{#", html)

    def test_order_detail_payment_sheet_and_stacked_table(self):
        self.client.force_login(self.customer)
        # Prefer an order that still accepts uploads so the sheet markup is rendered.
        uploadable = None
        for order in Order.objects.filter(customer=self.customer):
            if order.can_accept_additional_payment():
                uploadable = order
                break
        if uploadable is None:
            uploadable = self.order
            uploadable.agreed_total = None
            uploadable.save(update_fields=["agreed_total"])
        resp = self.client.get(reverse("order_detail", args=[uploadable.order_id]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("table-responsive-cards", html)
        self.assertIn("md:landscape:grid-cols-2", html)
        self.assertIn("data-payment-sheet", html)
        self.assertIn("data-payment-sheet-open", html)
        self.assertIn('capture="environment"', html)

    def test_modal_component_uses_dvh(self):
        from pathlib import Path

        path = Path(__file__).resolve().parents[3] / "templates" / "components" / "modal.html"
        source = path.read_text(encoding="utf-8")
        self.assertIn("90dvh", source)
        self.assertNotIn("90vh", source)
