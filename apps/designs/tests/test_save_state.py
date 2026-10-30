"""
Stage G: save-state reliability, navigation guards, submission readiness.

Django tests cover server contracts + static source checks for client helpers.
Browser behavior is verified separately (see qa/stage_g_verify.js).
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


class SaveStateSourceTests(TestCase):
    """SOURCE-STRING: Stage G dirty/save/nav/readiness wiring in static JS + template."""

    def test_editor_page_save_state_machine(self):
        source = _read_static("js/editor_page.js")
        for token in (
            "BlytzEditorSaveState",
            "lastSavedFingerprint",
            "saveInFlight",
            "saveGeneration",
            "recomputeDirtyFromSnapshot",
            "beforeunload",
            "shouldWarnUnload",
            "allowUnloadOnce",
            "getSubmissionReadiness",
            "Unsaved changes",
            "Saving…",
            "Saved earlier revision; newer edits are unsaved.",
            "editorPageWired",
            "isCurvePreviewDirty",
        ):
            self.assertIn(token, source)

        # Must not mark Saved on failed HTTP / malformed JSON / network errors.
        self.assertIn('saveUiStatus = "error"', source)
        self.assertIn("formatSaveErrors", source)
        # Stale save must not clear newer dirty state.
        self.assertIn("live !== lastSavedFingerprint", source)
        self.assertIn('dirty ? "unsaved" : "saved"', source)
        # Concurrent saves blocked.
        self.assertIn("Save already in progress.", source)
        # Readiness must not call preparePersistPayload (would discard curve preview).
        readiness_idx = source.index("function getSubmissionReadiness")
        readiness_chunk = source[readiness_idx : readiness_idx + 4500]
        self.assertNotIn("preparePersistPayload()", readiness_chunk)
        self.assertIn("Non-destructive size/artwork probe", readiness_chunk)

    def test_contract_history_navigate_hook(self):
        source = _read_static("js/editor_contract.js")
        self.assertIn("onHistoryNavigate", source)
        self.assertIn("historyNavigateListeners", source)
        self.assertIn('notifyHistoryNavigate("undo"', source)
        self.assertIn('notifyHistoryNavigate("redo"', source)

    def test_curve_discard_recomputes_dirty(self):
        source = _read_static("js/editor_properties.js")
        self.assertIn("BlytzEditorSaveState", source)
        self.assertIn("recompute", source)
        # discardCurvePreview still restores baseline before recompute.
        self.assertIn("function discardCurvePreview", source)

    def test_editor_template_save_status_and_readiness(self):
        template = (
            Path(__file__).resolve().parents[3]
            / "templates"
            / "designs"
            / "editor.html"
        )
        self.assertTrue(template.is_file())
        text = template.read_text(encoding="utf-8")
        self.assertIn("data-editor-save-status", text)
        self.assertIn("data-editor-readiness", text)
        self.assertIn("Before you submit", text)
        self.assertIn("data-editor-status", text)

    def test_responsive_css_save_status_styles(self):
        source = _read_static("css/responsive.css")
        self.assertIn(".editor-save-status", source)
        self.assertIn(".editor-readiness-list", source)
        self.assertIn(".editor-status-stack", source)


class SaveStateEditorPageTests(TestCase):
    """Editor page still serves save/submit URLs and ownership stays intact."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="stageg@example.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="stageg-other@example.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.user,
            title="Stage G Draft",
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

    def test_editor_page_includes_save_status_markup(self):
        url = reverse("design_editor", kwargs={"pk": self.design.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("data-editor-save-status", content)
        self.assertIn("data-editor-readiness", content)
        self.assertIn("editor_page.js", content)
        self.assertIn(f"/app/designs/{self.design.pk}/save/", content)

    def test_save_success_still_persists_canvas(self):
        url = reverse("design_save", kwargs={"pk": self.design.pk})
        payload = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [
                    {
                        "type": "i-text",
                        "text": "Stage G",
                        "left": 40,
                        "top": 40,
                        "fontFamily": "Arial",
                        "blytzId": "b_stageg1",
                    }
                ],
            },
            "views": {"back": {"version": "6.6.1", "objects": []}},
        }
        import json

        response = self.client.post(
            url,
            {
                "canvas_json": json.dumps(payload),
                "title": "Stage G Saved",
                "garment_template": "tee",
                "garment_color": "white",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.design.refresh_from_db()
        self.assertEqual(self.design.title, "Stage G Saved")
        self.assertEqual(
            self.design.canvas_json["canvas"]["objects"][0]["text"], "Stage G"
        )

    def test_save_rejects_oversized_without_clearing_design(self):
        import json

        url = reverse("design_save", kwargs={"pk": self.design.pk})
        before = self.design.canvas_json
        # Inflate past 2 MiB with a large text payload (still valid-looking JSON).
        huge = "x" * (2 * 1024 * 1024 + 100)
        response = self.client.post(
            url,
            {
                "canvas_json": json.dumps(
                    {
                        "schema_version": 1,
                        "width": 800,
                        "height": 800,
                        "canvas": {
                            "version": "6.6.1",
                            "objects": [
                                {
                                    "type": "i-text",
                                    "text": huge,
                                    "left": 0,
                                    "top": 0,
                                    "fontFamily": "Arial",
                                    "blytzId": "b_huge",
                                }
                            ],
                        },
                        "views": {"back": {"version": "6.6.1", "objects": []}},
                    }
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get("ok", True))
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json, before)

    def test_non_owner_cannot_save(self):
        other_client = Client()
        other_client.force_login(self.other)
        url = reverse("design_save", kwargs={"pk": self.design.pk})
        response = other_client.post(
            url,
            {"canvas_json": "{}"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertIn(response.status_code, (403, 404))
