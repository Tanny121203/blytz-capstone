"""Server-side checks for Blytz canvas JSON schema_version 1 and editor assets."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import Design

User = get_user_model()

BLYTZ_V1_EMPTY = {
    "schema_version": 1,
    "width": 800,
    "height": 800,
    "canvas": {"version": "6.6.1", "objects": []},
}

LEGACY_EMPTY = {"version": 1, "objects": []}


class CanvasSchemaSaveTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="canvas-schema@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Schema design",
            garment_template="tee",
            garment_color="black",
            canvas_json=LEGACY_EMPTY,
        )

    def test_editor_page_serves_fabric_and_canvas_modules(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vendor/fabric/fabric.min.js")
        self.assertContains(response, "js/editor_canvas.js")
        self.assertContains(response, "js/editor_tools.js")
        self.assertContains(response, "js/editor_properties.js")
        self.assertContains(response, "js/editor_contract.js")
        self.assertContains(response, 'id="blytz-fabric-canvas"')
        self.assertContains(response, 'id="editor-canvas-host"')
        self.assertContains(response, 'id="editor-tool-panel"')
        self.assertContains(response, 'id="editor-properties-panel"')
        self.assertContains(response, 'id="editor-props-pill"')
        self.assertContains(response, 'id="ai-assistant"')
        self.assertContains(response, "js/ai_chat.js")
        self.assertContains(response, 'id="editor-toolbar"')
        self.assertContains(response, 'data-editor-action="add-text"')
        self.assertContains(response, 'data-editor-action="multi-select"')
        self.assertContains(response, 'data-editor-action="delete"')
        self.assertContains(response, 'data-editor-action="elements"')
        self.assertContains(response, "data-editor-image-input")
        self.assertContains(response, "data-ai-form")
        self.assertContains(response, "data-ai-turn")
        self.assertContains(response, "data-ai-suggest-url")
        self.assertContains(response, "editor-shell")
        # Without GEMINI_API_KEY, copy explains local demo fallback.
        self.assertContains(response, "local demo candidates")
        self.assertNotContains(response, "four local demo candidates")
        self.assertNotContains(response, "data-ai-apply")
        self.assertNotContains(response, "Apply to canvas")
        # Multi-line Django {# #} comments can leak into HTML; keep this gone.
        self.assertNotContains(response, "Wrap size is set in JS")
        self.assertNotContains(response, "max-w-[800px] may be absent")
        # FR-14: no export/download controls in the editor chrome.
        self.assertNotContains(response, "download")
        self.assertNotContains(response, "Export")

    def test_save_persists_blytz_schema_v1_envelope(self):
        self.client.force_login(self.customer)
        payload = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [
                    {
                        "type": "IText",
                        "text": "Hello",
                        "left": 100,
                        "top": 120,
                        "fontSize": 28,
                        "fill": "#0a0a0a",
                    }
                ],
            },
        }
        response = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(payload)},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))

        self.design.refresh_from_db()
        stored = self.design.canvas_json
        self.assertEqual(stored.get("schema_version"), 1)
        self.assertEqual(stored.get("width"), 800)
        self.assertEqual(stored.get("height"), 800)
        self.assertIsInstance(stored.get("canvas"), dict)
        objects = stored["canvas"].get("objects") or []
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].get("text"), "Hello")

        editor = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(editor.status_code, 200)
        # Initial JSON is HTML-escaped into data-canvas-json; unescaped content must round-trip.
        self.assertIn("schema_version", editor.context["canvas_json_initial"])
        reloaded = json.loads(editor.context["canvas_json_initial"])
        self.assertEqual(reloaded["schema_version"], 1)
        self.assertEqual(reloaded["canvas"]["objects"][0]["text"], "Hello")

    def test_legacy_empty_stub_still_accepted_by_save(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(LEGACY_EMPTY)},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json.get("version"), 1)
        self.assertEqual(self.design.canvas_json.get("objects"), [])

    def test_submit_snapshot_preserves_schema_v1_payload(self):
        from decimal import Decimal
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone
        from PIL import Image

        from apps.orders.models import Order, PaymentChannel

        channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Schema GCash",
            account_name="Blytz",
            account_number="09170002222",
            is_active=True,
        )
        buffer = BytesIO()
        Image.new("RGB", (16, 16), color=(10, 10, 10)).save(buffer, format="PNG")
        proof = SimpleUploadedFile(
            "proof.png", buffer.getvalue(), content_type="image/png"
        )

        self.client.force_login(self.customer)
        payload = dict(BLYTZ_V1_EMPTY)
        payload["canvas"] = {
            "version": "6.6.1",
            "objects": [{"type": "IText", "text": "Submit me", "left": 40, "top": 40}],
        }
        front = SimpleUploadedFile(
            "preview_front.png", buffer.getvalue(), content_type="image/png"
        )
        back = SimpleUploadedFile(
            "preview_back.png", buffer.getvalue(), content_type="image/png"
        )
        response = self.client.post(
            reverse("design_submit", args=[self.design.pk]),
            {
                "channel": channel.pk,
                "amount_claimed": "100.00",
                "canvas_json": json.dumps(payload),
                "window_started_at": timezone.now().isoformat(),
                "proof_file": proof,
                "preview_image": front,
                "preview_back_image": back,
            },
        )
        order = Order.objects.get(design=self.design)
        self.assertRedirects(
            response, reverse("order_detail", kwargs={"order_id": order.order_id})
        )
        snap = order.canvas_json_snapshot
        self.assertEqual(snap.get("schema_version"), 1)
        self.assertEqual(snap["canvas"]["objects"][0]["text"], "Submit me")
        self.assertEqual(order.payments.first().amount_claimed, Decimal("100.00"))

    def test_editor_exposes_readiness_helpers_in_contract_script(self):
        """Static contract script must expose readiness/persist helpers used by editor_page."""
        from django.contrib.staticfiles import finders

        path = finders.find("js/editor_contract.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        for token in (
            "getLoadState",
            "canPersist",
            "whenReady",
            "preparePersistPayload",
            "getPersistBlockReason",
            "validateCanvasJSON",
            "applyCanvasJSON",
            "previewCanvasJSON",
            "validateObjectsAllowlist",
        ):
            self.assertIn(token, source)

    def test_editor_canvas_has_central_commit_and_blytz_id(self):
        from django.contrib.staticfiles import finders

        path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("function commitEdit", source)
        self.assertIn("beforeCommitHooks", source)
        self.assertIn("afterCommitHooks", source)
        self.assertIn("blytzId", source)
        self.assertIn("text:editing:exited", source)
        self.assertIn("validateObjectsAllowlist", source)
        self.assertRegex(source, r'["\']blytzId["\']')
        # Stage 0: duplicates must mint a new id; undo restores active view.
        self.assertIn("function forceBlytzId", source)
        self.assertIn("function duplicateLayerName", source)
        self.assertIn("historyActiveViews", source)
        self.assertIn("forceReencode", source)

    def test_editor_insertion_constants_source_checks(self):
        """Source checks: Stage 3b constants that later stages / panels rely on."""
        from django.contrib.staticfiles import finders

        canvas_path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(canvas_path)
        with open(canvas_path, encoding="utf-8") as fh:
            canvas_src = fh.read()
        self.assertRegex(canvas_src, r"IMAGE_INSERT_BUDGET_RATIO\s*=\s*0\.8")
        self.assertIn("var ALLOWED_FONTS", canvas_src)
        self.assertIn('"Arial"', canvas_src)
        self.assertIn('"Verdana"', canvas_src)
        self.assertIn('"Georgia"', canvas_src)
        self.assertIn('"Times New Roman"', canvas_src)
        self.assertIn('"Courier New"', canvas_src)
        self.assertIn('"Impact"', canvas_src)
        self.assertIn("ALLOWED_FONTS: ALLOWED_FONTS", canvas_src)

        tools_path = finders.find("js/editor_tools.js")
        self.assertIsNotNone(tools_path)
        with open(tools_path, encoding="utf-8") as fh:
            tools_src = fh.read()
        self.assertIn("var GRAPHICS_DEFS", tools_src)
        self.assertIn("star:", tools_src)
        self.assertIn("arrow:", tools_src)
        self.assertIn("badge:", tools_src)
        self.assertIn("heart:", tools_src)
        self.assertIn("lightning:", tools_src)
        self.assertIn("starburst:", tools_src)
        self.assertIn("GRAPHICS_DEFS: GRAPHICS_DEFS", tools_src)
        self.assertIn('id === "upload"', tools_src)
        self.assertIn("editor-tool-panel", tools_src)

    def test_editor_properties_and_layers_source_checks(self):
        """SOURCE-STRING: Stage 3c palette, registry, clamps, blytzName, layer renderer."""
        from django.contrib.staticfiles import finders

        canvas_path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(canvas_path)
        with open(canvas_path, encoding="utf-8") as fh:
            canvas_src = fh.read()
        self.assertIn("var COLOR_PRESETS", canvas_src)
        self.assertIn("var PROP_LIMITS", canvas_src)
        self.assertIn('"blytzName"', canvas_src)
        self.assertIn("COLOR_PRESETS: COLOR_PRESETS", canvas_src)
        self.assertIn("bringObjectForward", canvas_src)
        self.assertIn("sendObjectBackwards", canvas_src)

    def test_hardening_image_and_scan_source_checks(self):
        """SOURCE-STRING: IMAGE_* constants, scanCanvasPayload, cross-reference comments."""
        from django.contrib.staticfiles import finders
        from pathlib import Path

        canvas_path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(canvas_path)
        with open(canvas_path, encoding="utf-8") as fh:
            canvas_src = fh.read()
        for token in (
            "IMAGE_INPUT_LIMIT_BYTES",
            "IMAGE_MAX_EDGE",
            "IMAGE_TARGET_BYTES",
            "IMAGE_QUALITY_STEPS",
            "IMAGE_EDGE_STEPS",
            "IMAGE_MAX_PIXELS",
            "function scanCanvasPayload",
            "apps/designs/canvas_safety.py",
            "measureEnvelopeBytes",
            "fabricVersionOk",
        ):
            self.assertIn(token, canvas_src)

        safety = Path(__file__).resolve().parents[1] / "canvas_safety.py"
        self.assertTrue(safety.is_file())
        safety_src = safety.read_text(encoding="utf-8")
        self.assertIn("scanCanvasPayload", safety_src)
        self.assertIn("static/js/editor_canvas.js", safety_src)

        props_path = finders.find("js/editor_properties.js")
        self.assertIsNotNone(props_path)
        with open(props_path, encoding="utf-8") as fh:
            props_src = fh.read()
        self.assertIn("var PROPERTY_REGISTRY", props_src)
        self.assertIn("PROPERTY_REGISTRY: PROPERTY_REGISTRY", props_src)
        self.assertIn("setPositionByOrigin", props_src)
        self.assertIn("runSilent", props_src)

        tools_path = finders.find("js/editor_tools.js")
        self.assertIsNotNone(tools_path)
        with open(tools_path, encoding="utf-8") as fh:
            tools_src = fh.read()
        self.assertIn("function renderLayerRow", tools_src)
        self.assertIn("function layerLabel", tools_src)
        self.assertIn('id === "layers"', tools_src)
        self.assertIn("No layers yet.", tools_src)

    def test_ai_chat_module_keeps_mock_and_live_adapters(self):
        """Stage O: live fetch to design AI URL; mock fallback; no hard-coded keys."""
        from django.contrib.staticfiles import finders

        path = finders.find("js/ai_chat.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("mockAssistantRespond", source)
        self.assertIn("liveAssistantRespond", source)
        self.assertIn("assistantRespond", source)
        self.assertIn("previewCanvasJSON", source)
        self.assertIn("onCommittedChange", source)
        self.assertIn("CANDIDATES_PER_TURN", source)
        self.assertIn("contextFingerprint", source)
        self.assertRegex(source, r"CANDIDATES_PER_TURN\s*=\s*2")
        self.assertIn("fetch(", source)
        self.assertIn("data-ai-suggest-url", source)
        # Header value only — must not construct XHR transport.
        self.assertNotIn("new XMLHttpRequest", source)
        self.assertNotIn("apiKey", source)
        self.assertNotIn("openai", source.lower())
        # Must not embed a Gemini secret; "gemini" may appear only as a source label.
        self.assertNotRegex(source, r"AIza[0-9A-Za-z_-]{10,}")
        self.assertNotIn("GEMINI_API_KEY", source)
        # §5.4: no Apply confirmation gate; commit is via real canvas edits.
        self.assertNotIn("Apply to canvas", source)
        self.assertNotIn("openPreview", source)

    def test_ai_chat_mock_builds_two_independent_candidates(self):
        """Static mock builder must emit exactly two deep-cloned schema v1 envelopes."""
        from django.contrib.staticfiles import finders

        path = finders.find("js/ai_chat.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("mock-wordmark", source)
        self.assertIn("mock-monogram", source)
        self.assertNotIn("mock-badge", source)
        self.assertNotIn("mock-underline", source)
        self.assertIn("deepClone", source)
        self.assertIn("validateCandidateSet", source)
        self.assertIn("discardCandidates", source)
        self.assertIn("exactly two valid candidates", source)
        self.assertIn('data-ai-candidates', source)

    def test_editor_canvas_sizes_from_locked_workspace_not_host_content(self):
        """Regression: display size must use #editor-root, not content-grown host height."""
        from django.contrib.staticfiles import finders

        path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("availableDisplaySize", source)
        self.assertIn('getElementById("editor-root")', source)
        self.assertIn("lastAppliedDisplaySize", source)
        self.assertIn("scheduleResponsiveSize", source)
        # Must not observe the wrap (feedback loop risk).
        self.assertIn('observe(workspace)', source)

    def test_responsive_css_locks_editor_shell_height(self):
        """Regression: editor shell must be viewport-height locked against AI panel growth."""
        from django.contrib.staticfiles import finders

        path = finders.find("css/responsive.css")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn(".editor-shell[data-editor-page]", source)
        self.assertIn("calc(100dvh - 8rem)", source)
        self.assertIn("overflow: hidden", source)
        self.assertIn(".ai-turn-panel", source)
        self.assertIn("[data-ai-candidates]", source)

    def test_unknown_schema_version_still_round_trips_on_server_untouched(self):
        """Server must keep opaque JSON; client is responsible for blocking overwrite."""
        self.client.force_login(self.customer)
        unsupported = {"schema_version": 99, "canvas": {"objects": [{"type": "secret"}]}}
        self.design.canvas_json = unsupported
        self.design.save(update_fields=["canvas_json"])
        response = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(response.status_code, 200)
        initial = json.loads(response.context["canvas_json_initial"])
        self.assertEqual(initial.get("schema_version"), 99)
        self.assertEqual(initial["canvas"]["objects"][0]["type"], "secret")
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json["schema_version"], 99)

    def test_save_rejects_canvas_json_over_2_mib(self):
        from apps.designs.forms import MAX_CANVAS_JSON_BYTES, DesignSaveForm

        self.assertEqual(MAX_CANVAS_JSON_BYTES, 2 * 1024 * 1024)
        # '{"pad":"' (8) + pad + '"}' (2) → one byte over the cap.
        over = '{"pad":"' + ("a" * (MAX_CANVAS_JSON_BYTES - 9)) + '"}'
        self.assertEqual(len(over.encode("utf-8")), MAX_CANVAS_JSON_BYTES + 1)
        form = DesignSaveForm(data={"canvas_json": over})
        self.assertFalse(form.is_valid())
        self.assertIn("canvas_json", form.errors)

    def test_save_accepts_canvas_json_exactly_at_2_mib(self):
        from apps.designs.forms import MAX_CANVAS_JSON_BYTES, DesignSaveForm

        prefix = '{"pad":"'
        suffix = '"}'
        pad_len = MAX_CANVAS_JSON_BYTES - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
        exact = prefix + ("a" * pad_len) + suffix
        self.assertEqual(len(exact.encode("utf-8")), MAX_CANVAS_JSON_BYTES)
        form = DesignSaveForm(data={"canvas_json": exact})
        self.assertTrue(form.is_valid())
        self.assertIn("pad", form.cleaned_data["canvas_json"])

    def test_save_accepts_normal_blytz_payload_unaffected_by_size_cap(self):
        self.client.force_login(self.customer)
        payload = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {"version": "6.6.1", "objects": []},
        }
        response = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(payload)},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))

    def test_parse_canvas_json_dict_exactly_at_2_mib_passes(self):
        from apps.designs.forms import MAX_CANVAS_JSON_BYTES, _parse_canvas_json

        # Build a dict whose compact UTF-8 JSON is exactly the cap.
        prefix = '{"pad":"'
        suffix = '"}'
        pad_len = (
            MAX_CANVAS_JSON_BYTES
            - len(prefix.encode("utf-8"))
            - len(suffix.encode("utf-8"))
        )
        exact_str = prefix + ("a" * pad_len) + suffix
        self.assertEqual(len(exact_str.encode("utf-8")), MAX_CANVAS_JSON_BYTES)
        data = json.loads(exact_str)
        parsed = _parse_canvas_json(data)
        self.assertEqual(parsed.get("pad"), "a" * pad_len)

    def test_parse_canvas_json_dict_one_byte_over_2_mib_fails(self):
        from django import forms as django_forms

        from apps.designs.forms import MAX_CANVAS_JSON_BYTES, _parse_canvas_json

        prefix = '{"pad":"'
        suffix = '"}'
        pad_len = (
            MAX_CANVAS_JSON_BYTES
            - len(prefix.encode("utf-8"))
            - len(suffix.encode("utf-8"))
            + 1
        )
        over_str = prefix + ("a" * pad_len) + suffix
        self.assertEqual(len(over_str.encode("utf-8")), MAX_CANVAS_JSON_BYTES + 1)
        data = json.loads(over_str)
        with self.assertRaises(django_forms.ValidationError):
            _parse_canvas_json(data)
