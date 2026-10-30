"""BEHAVIOR tests for shared canvas safety (schema_version 1 only)."""

import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.designs.canvas_safety import CanvasSafetyError, scan_canvas_payload, type_key
from apps.designs.forms import DesignSaveForm, DesignSubmitForm
from apps.designs.models import Design
from apps.orders.models import PaymentChannel

User = get_user_model()

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

DATA_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _v1(objects, **extra):
    payload = {
        "schema_version": 1,
        "width": 800,
        "height": 800,
        "canvas": {"version": "6.6.1", "objects": objects},
    }
    payload.update(extra)
    return payload


class CanvasSafetyUnitTests(TestCase):
    """BEHAVIOR: typeKey and scan_canvas_payload unit rules."""

    def test_type_key_strips_non_letters(self):
        self.assertEqual(type_key("i-text"), "itext")
        self.assertEqual(type_key({"type": "IText"}), "itext")
        self.assertEqual(type_key("Group"), "group")

    def test_accepts_legitimate_v1_payload(self):
        payload = _v1(
            [
                {
                    "type": "Rect",
                    "left": 10,
                    "top": 10,
                    "width": 40,
                    "height": 40,
                    "fill": "#111111",
                    "blytzId": "a1",
                    "blytzName": "Rectangle",
                },
                {
                    "type": "IText",
                    "text": "Hello https://example.com",
                    "left": 20,
                    "top": 20,
                    "blytzId": "a2",
                    "blytzName": "Text",
                },
                {
                    "type": "Image",
                    "src": DATA_PNG,
                    "left": 30,
                    "top": 30,
                    "blytzId": "a3",
                    "blytzName": "Image",
                },
                {
                    "type": "Polygon",
                    "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 5, "y": 10}],
                    "fill": "#1a1a1a",
                },
                {
                    "type": "Path",
                    "path": [["M", 0, 0], ["L", 10, 10]],
                    "fill": "#1a1a1a",
                },
            ]
        )
        self.assertTrue(scan_canvas_payload(payload)["ok"])

    def test_rejects_external_https_src(self):
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(
                _v1([{"type": "Image", "src": "https://evil.example/x.png"}])
            )

    def test_rejects_http_protocol_relative_javascript_relative(self):
        for src in (
            "http://evil.example/x.png",
            "//evil.example/x.png",
            "javascript:alert(1)",
            "/media/x.png",
            "file:///tmp/x.png",
        ):
            with self.assertRaises(CanvasSafetyError, msg=src):
                scan_canvas_payload(_v1([{"type": "Image", "src": src}]))

    def test_rejects_pattern_fill_with_source(self):
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(
                _v1([{"type": "Rect", "fill": {"source": DATA_PNG, "repeat": "repeat"}}])
            )

    def test_rejects_group_and_unknown_type(self):
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(_v1([{"type": "group", "objects": []}]))
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(_v1([{"type": "evil"}]))

    def test_rejects_background_image(self):
        payload = _v1([])
        payload["canvas"]["backgroundImage"] = {"type": "Image", "src": DATA_PNG}
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(payload)

    def test_accepts_text_containing_https(self):
        self.assertTrue(
            scan_canvas_payload(
                _v1([{"type": "IText", "text": "see https://example.com/docs"}])
            )["ok"]
        )

    def test_rejects_depth_over_limit(self):
        node = {"type": "Rect", "fill": "#000"}
        # Nest clipPath deeper than MAX_DEPTH.
        cur = node
        for _ in range(25):
            nxt = {"type": "Rect", "fill": "#000"}
            cur["clipPath"] = nxt
            cur = nxt
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(_v1([node]))

    def test_views_front_and_unknown_rejected_back_ok_and_external_rejected(self):
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(_v1([], views={"front": {"objects": []}}))
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(_v1([], views={"sleeve": {"objects": []}}))
        ok_payload = _v1(
            [{"type": "Rect", "fill": "#111"}],
            views={"back": {"version": "6.6.1", "objects": [{"type": "Ellipse", "fill": "#222"}]}},
        )
        self.assertTrue(scan_canvas_payload(ok_payload)["ok"])
        bad_back = _v1(
            [],
            views={
                "back": {
                    "objects": [{"type": "Image", "src": "https://evil.example/a.png"}]
                }
            },
        )
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(bad_back)


class CanvasSafetyFormTests(TestCase):
    """BEHAVIOR: save and submit forms apply v1 safety; non-v1 stays opaque."""

    def setUp(self):
        self.customer = User.objects.create_user(
            email="safety@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Safety design",
            garment_template="tee",
            garment_color="black",
            canvas_json={"version": 1, "objects": []},
        )
        self.channel = PaymentChannel.objects.create(
            kind=PaymentChannel.Kind.GCASH,
            display_name="Test GCash Safety",
            account_name="Blytz",
            account_number="09170002222",
            is_active=True,
        )

    def test_save_accepts_legitimate_v1(self):
        payload = _v1(
            [
                {"type": "Rect", "fill": "#111", "blytzId": "r1", "blytzName": "Rectangle"},
                {"type": "IText", "text": "Hi", "blytzId": "t1"},
                {"type": "Image", "src": DATA_PNG, "blytzId": "i1"},
            ]
        )
        form = DesignSaveForm(data={"canvas_json": json.dumps(payload)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_rejects_external_image(self):
        payload = _v1([{"type": "Image", "src": "https://evil.example/x.png"}])
        form = DesignSaveForm(data={"canvas_json": json.dumps(payload)})
        self.assertFalse(form.is_valid())
        self.assertIn("canvas_json", form.errors)

    def test_schema_99_untouched(self):
        unsupported = {"schema_version": 99, "canvas": {"objects": [{"type": "secret"}]}}
        form = DesignSaveForm(data={"canvas_json": json.dumps(unsupported)})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["canvas_json"]["schema_version"], 99)

    def test_unsupported_legacy_stub_rejected_on_save(self):
        """Non-empty pre-Fabric stubs match client isUnsupportedLegacy — reject persist."""
        legacy = {"version": 1, "objects": [{"type": "text"}]}
        form = DesignSaveForm(data={"canvas_json": json.dumps(legacy)})
        self.assertFalse(form.is_valid())
        self.assertIn("canvas_json", form.errors)

    def test_legacy_empty_stub_still_accepted(self):
        """Empty legacy stubs remain supported (client loads as empty v1 envelope)."""
        legacy = {"version": 1, "objects": []}
        form = DesignSaveForm(data={"canvas_json": json.dumps(legacy)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_raw_fabric_canvas_still_accepted(self):
        """Raw Fabric (string version + objects) remains supported; client wraps to v1."""
        raw = {"version": "6.6.1", "objects": [{"type": "rect", "width": 10, "height": 10}]}
        form = DesignSaveForm(data={"canvas_json": json.dumps(raw)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_submit_rejects_group(self):
        payload = _v1([{"type": "group", "objects": []}])
        form = DesignSubmitForm(
            data={
                "channel": self.channel.pk,
                "amount_claimed": "100.00",
                "canvas_json": json.dumps(payload),
                "window_started_at": "2020-01-01T00:00:00+00:00",
            },
            files={
                "proof_file": SimpleUploadedFile(
                    "proof.png", TINY_PNG, content_type="image/png"
                ),
                "preview_image": SimpleUploadedFile(
                    "preview_front.png", TINY_PNG, content_type="image/png"
                ),
                "preview_back_image": SimpleUploadedFile(
                    "preview_back.png", TINY_PNG, content_type="image/png"
                ),
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("canvas_json", form.errors)

    def test_save_endpoint_rejects_evil_type_without_writing(self):
        self.client.force_login(self.customer)
        before = self.design.canvas_json
        payload = _v1([{"type": "evil"}])
        response = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(payload)},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json, before)
