"""
Stage H / H.1: customer-facing design preview / final review.

Django tests cover static source contracts + editor markup.
Browser behavior is verified separately (see qa/stage_h_verify.js).
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


def _preview_chunk(source: str) -> str:
    preview_idx = source.index("Stage H: design preview")
    return source[preview_idx:]


class DesignPreviewSourceTests(TestCase):
    """SOURCE-STRING: Stage H preview wiring in static JS + CSS + template."""

    def test_editor_page_preview_machine(self):
        source = _read_static("js/editor_page.js")
        for token in (
            "BlytzEditorDesignPreview",
            "openDesignPreview",
            "closeDesignPreview",
            "requestPreviewRender",
            "previewRequestGen",
            "includeGarment: true",
            "clearPreviewImageResources",
            "revokeObjectURL",
            "Unsaved changes. This is a live draft mock-up",
            "data-design-preview",
            "onPreviewKeydown",
            "Escape",
            "performSave()",
            "getSubmissionReadiness",
            "design-preview-modal",
        ):
            self.assertIn(token, source)

        # Must not claim unsaved draft is a saved final.
        self.assertIn("not a saved final", source)
        # Presentation-only: must not call commitEdit for preview ops.
        preview_chunk = _preview_chunk(source)
        self.assertNotIn("commitEdit(", preview_chunk)
        self.assertNotIn("setActiveView(", preview_chunk)
        # Stale async guard.
        self.assertIn("previewStillOpenForGen", source)
        self.assertIn("gen === previewRequestGen", source)
        # Reuses existing save path (performSave), not a parallel submit.
        self.assertNotIn("design_submit", preview_chunk)
        self.assertIn("Close this preview and use Submit", source)

    def test_preview_save_triggers_refresh_not_duplicate_save(self):
        """H.1: clean save SUCCESS refreshes mock-up; Preview Save uses performSave only."""
        source = _read_static("js/editor_page.js")
        preview_chunk = _preview_chunk(source)

        self.assertIn("refreshPreviewAfterSuccessfulSave", source)
        self.assertIn("triggerPreviewRefreshAfterSave", source)
        self.assertIn("Updating saved mock-up", source)
        self.assertIn("matchesSavedFingerprintForRefresh", source)
        self.assertIn("getRenderStatus", source)

        # Success path wires refresh only after clean saved state (not on error).
        success_idx = source.index('saveUiStatus = dirty ? "unsaved" : "saved"')
        success_chunk = source[success_idx : success_idx + 900]
        self.assertIn("triggerPreviewRefreshAfterSave", success_chunk)
        self.assertIn('saveUiStatus === "saved"', success_chunk)

        # Failed / network save paths must not call preview refresh.
        perform_idx = source.index("function performSave")
        perform_end = source.index("function shouldWarnUnload")
        perform_chunk = source[perform_idx:perform_end]
        # Refresh trigger only in success branch (typeof check + call).
        self.assertEqual(perform_chunk.count("triggerPreviewRefreshAfterSave"), 2)
        else_idx = perform_chunk.index("} else {\n            dirty = true;")
        catch_chunk = perform_chunk[else_idx:]
        self.assertNotIn("triggerPreviewRefreshAfterSave", catch_chunk)

        # Preview Save: already-saved skips unnecessary performSave; no second save API.
        self.assertIn(
            'if (!dirty && saveUiStatus === "saved" && !saveInFlight)',
            preview_chunk,
        )
        self.assertIn("no unnecessary save", preview_chunk.lower())
        save_btn_idx = preview_chunk.index("data-design-preview-save")
        # Handler for preview save only (before editor chrome saveBtn binding).
        preview_save_handler = preview_chunk[
            save_btn_idx : preview_chunk.index("if (saveBtn)", save_btn_idx)
        ]
        self.assertEqual(preview_save_handler.count("performSave()"), 1)
        self.assertNotIn("fetch(saveUrl", preview_save_handler)

        # Render failure after save keeps Saved; distinct retry; no blank wipe on fail.
        self.assertIn("Your design remains saved", source)
        self.assertIn("data-design-preview-refresh-retry", source)
        self.assertIn("previewRenderStatus", source)
        # Post-save refresh must not clear image before attempting render.
        refresh_idx = source.index("function refreshPreviewAfterSuccessfulSave")
        refresh_fn = source[refresh_idx : refresh_idx + 3500]
        self.assertNotIn("clearPreviewImageResources()", refresh_fn)
        self.assertIn("assignPreviewImage", refresh_fn)
        self.assertIn("showRetry: true", refresh_fn)

    def test_preview_race_and_non_mutation_guards(self):
        source = _read_static("js/editor_page.js")
        preview_chunk = _preview_chunk(source)
        self.assertIn("previewStillOpenForGen(gen)", preview_chunk)
        self.assertIn("matchesSavedFingerprintForRefresh()", preview_chunk)
        # Closed preview / stale gen must noop (bump gen on close).
        close_idx = source.index("function closeDesignPreview")
        close_fn = source[close_idx : close_idx + 1200]
        self.assertIn("previewRequestGen += 1", close_fn)
        self.assertIn("previewOpen = false", close_fn)
        # No live editor mutation from preview machine.
        for banned in (
            "commitEdit(",
            "setActiveView(",
            "loadCanvasJSON(",
            "setGarmentState(",
        ):
            self.assertNotIn(banned, preview_chunk)

    def test_preview_uses_getPreviewPNG_garment_path(self):
        source = _read_static("js/editor_page.js")
        self.assertIn("getPreviewPNG", source)
        self.assertIn("{ view: target, includeGarment: true }", source)
        canvas = _read_static("js/editor_canvas.js")
        self.assertIn("function getPreviewPNG", canvas)
        self.assertIn("includeGarment", canvas)
        # Offscreen / non-mutating export path for inactive view.
        self.assertIn("Never switches live view", canvas)
        # Live active-view raster must restore selection after discarding handles.
        art_idx = canvas.index("function artworkDataURL()")
        art_chunk = canvas[art_idx : art_idx + 700]
        self.assertIn("getActiveObject()", art_chunk)
        self.assertIn("discardActiveObject()", art_chunk)
        self.assertIn("setActiveObject(prior)", art_chunk)

    def test_editor_template_preview_markup(self):
        template = (
            Path(__file__).resolve().parents[3]
            / "templates"
            / "designs"
            / "editor.html"
        )
        self.assertTrue(template.is_file())
        text = template.read_text(encoding="utf-8")
        for token in (
            'data-editor-preview',
            'id="design-preview-modal"',
            "data-design-preview-modal",
            "data-design-preview-img",
            'data-design-preview-side="front"',
            'data-design-preview-side="back"',
            "data-design-preview-save-status",
            "data-design-preview-readiness",
            "data-design-preview-honesty",
            "data-design-preview-refresh-retry",
            "Retry mock-up",
            "Back to edit",
            "?v=stage-h1",
            "role=\"dialog\"",
            'aria-modal="true"',
        ):
            self.assertIn(token, text)
        # Prefer review + existing Submit — no nested payment form in preview.
        preview_start = text.index("design-preview-modal")
        preview_end = text.index("payment-modal")
        preview_html = text[preview_start:preview_end]
        self.assertNotIn("payment-submit-form", preview_html)
        self.assertNotIn('name="proof_file"', preview_html)

    def test_responsive_css_preview_styles(self):
        source = _read_static("css/responsive.css")
        for token in (
            ".design-preview-side-tabs",
            ".design-preview-frame",
            ".design-preview-honesty",
            ".design-preview-refresh-retry",
            "#design-preview-modal",
            "Stage H",
        ):
            self.assertIn(token, source)


class DesignPreviewEditorPageTests(TestCase):
    """Editor page still serves ownership-safe editor with preview entry points."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="stageh@example.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="stageh-other@example.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.user,
            title="Stage H Draft",
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

    def test_editor_page_includes_preview_markup(self):
        url = reverse("design_editor", kwargs={"pk": self.design.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("data-editor-preview", content)
        self.assertIn("design-preview-modal", content)
        self.assertIn("data-design-preview-img", content)
        self.assertIn("data-design-preview-refresh-retry", content)
        self.assertIn("editor_page.js", content)
        self.assertIn("?v=stage-h1", content)
        self.assertIn(f"/app/designs/{self.design.pk}/save/", content)

    def test_non_owner_cannot_open_editor(self):
        other_client = Client()
        other_client.force_login(self.other)
        url = reverse("design_editor", kwargs={"pk": self.design.pk})
        response = other_client.get(url)
        self.assertIn(response.status_code, (403, 404))

    def test_save_still_works_after_preview_stage(self):
        """Preview is client-only — save contract unchanged."""
        import json

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
                        "text": "Stage H",
                        "left": 40,
                        "top": 40,
                        "fontFamily": "Arial",
                        "blytzId": "b_stageh1",
                    }
                ],
            },
            "views": {"back": {"version": "6.6.1", "objects": []}},
        }
        response = self.client.post(
            url,
            {
                "canvas_json": json.dumps(payload),
                "title": "Stage H Saved",
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
        self.assertEqual(self.design.title, "Stage H Saved")
        self.assertEqual(
            self.design.canvas_json["canvas"]["objects"][0]["text"], "Stage H"
        )
