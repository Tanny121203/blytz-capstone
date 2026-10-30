"""
Stage I: submission workflow / design-review hardening.

Django tests cover server duplicate/JSON contracts + static source checks
for client submit locks. Browser behavior: qa/stage_i_verify.js.
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse

from apps.designs.models import Design

User = get_user_model()


def _read_static(name: str) -> str:
    path = finders.find(name)
    assert path is not None, f"static file missing: {name}"
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class SubmitWorkflowSourceTests(TestCase):
    """SOURCE-STRING: Stage I submit lock / fingerprint / no-false-success."""

    def test_editor_page_submit_hardening_machine(self):
        source = _read_static("js/editor_page.js")
        for token in (
            "Stage I",
            "submitInFlight",
            "submitGeneration",
            "isSubmitInFlight",
            "finishSubmitFailure",
            "submitFingerprint",
            "Design changed during submission",
            "A submission is already in progress",
            "submit_inflight",
            "Generating previews…",
            "Submitting…",
        ):
            self.assertIn(token, source)

        # Must not allowUnload before server confirms success.
        form_idx = source.index('form.addEventListener("submit"')
        # Handler runs through success/failure; keep enough of the body.
        form_end = source.index("window.BlytzEditorSaveState", form_idx)
        form_chunk = source[form_idx:form_end]
        self.assertIn("allowUnloadOnce()", form_chunk)
        unload_idx = form_chunk.index("allowUnloadOnce()")
        fetch_idx = form_chunk.index("fetch(form.action")
        redirect_idx = form_chunk.index("window.location.href = res.data.redirect")
        # Exemption only after fetch returns, immediately before confirmed navigation.
        self.assertGreater(unload_idx, fetch_idx)
        self.assertLess(unload_idx, redirect_idx)
        self.assertEqual(form_chunk.count("allowUnloadOnce()"), 1)

        # Duplicate client submit blocked at handler entry.
        self.assertIn("if (submitInFlight)", form_chunk)
        # Mutation during async preview aborts with fingerprint compare.
        self.assertIn("liveFp !== submitFingerprint", form_chunk)
        # Snapshot from preparePersistPayload rebound into POST body.
        self.assertIn('body.set("canvas_json", prepared.jsonString)', form_chunk)
        self.assertIn("renderFrozenPreview", form_chunk)
        self.assertIn("frozenEnvelope", form_chunk)
        self.assertIn("garmentSnap", form_chunk)
        self.assertNotIn("getPreviewPNG", form_chunk)
        # Stale generation ignored.
        self.assertIn("gen !== submitGeneration", form_chunk)

        # Readiness includes submit_inflight; re-checked at send time.
        readiness_idx = source.index("function getSubmissionReadiness")
        readiness_chunk = source[readiness_idx : readiness_idx + 5500]
        self.assertIn('id: "submit_inflight"', readiness_chunk)
        self.assertIn("readinessAtSend", form_chunk)

        # Save must not compete with an in-flight submit.
        perform_idx = source.index("function performSave")
        perform_chunk = source[perform_idx : perform_idx + 400]
        self.assertIn("submitInFlight", perform_chunk)

        # Cancel must not claim "nothing recorded" while submit POST may succeed.
        cancel_idx = source.index("function cancelPayment")
        cancel_chunk = source[cancel_idx : cancel_idx + 900]
        self.assertIn("submitInFlight", cancel_chunk)
        self.assertIn("Submission in progress", cancel_chunk)

    def test_submit_view_uses_select_for_update_and_json_already(self):
        views = (
            Path(__file__).resolve().parents[1] / "views.py"
        ).read_text(encoding="utf-8")
        self.assertIn("select_for_update()", views)
        self.assertIn("_submit_already_response", views)
        self.assertIn("_submit_conflict_response", views)
        self.assertIn("unique_order_per_design", views)
        self.assertIn("except IntegrityError:", views)
        self.assertIn('errors": {"design"', views)


class SubmitWorkflowEditorPageTests(TestCase):
    """Editor still serves submit form + Stage I probe hooks; ownership intact."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="stagei@example.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="stagei-other@example.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.user,
            title="Stage I Draft",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {"version": "6.6.1", "objects": []},
                "views": {"back": {"version": "6.6.1", "objects": []}},
            },
            garment_template="tee",
            garment_color="white",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_editor_includes_payment_submit_form_and_page_script(self):
        url = reverse("design_editor", kwargs={"pk": self.design.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("payment-submit-form", content)
        self.assertIn("submit-canvas-json", content)
        self.assertIn("editor_page.js", content)
        self.assertIn(f"/app/designs/{self.design.pk}/submit/", content)

    def test_other_customer_cannot_open_editor(self):
        self.client.force_login(self.other)
        response = self.client.get(
            reverse("design_editor", kwargs={"pk": self.design.pk})
        )
        self.assertEqual(response.status_code, 404)
