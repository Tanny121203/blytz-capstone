"""Focused tests: curved-text geometry, metadata, and nested-path safety."""

from __future__ import annotations

import unittest
from pathlib import Path

from apps.designs.canvas_safety import CanvasSafetyError, scan_canvas_payload
from apps.designs.text_curve import (
    CURVE_BULGE_FACTOR,
    apply_curve_to_props,
    build_arc_path_commands,
    clamp_curve_amount,
    clear_curve_from_props,
    curve_path_d,
    is_multiline_text,
    make_blytz_curve,
    normalize_curve_direction,
)


def _v1(objects):
    return {
        "schema_version": 1,
        "width": 800,
        "height": 800,
        "canvas": {"version": "6.6.1", "objects": objects},
        "views": {"back": {"version": "6.6.1", "objects": []}},
    }


class CurveGeometryTests(unittest.TestCase):
    def test_clamp_and_direction(self):
        self.assertEqual(clamp_curve_amount(0.5), 0.5)
        self.assertEqual(clamp_curve_amount(-1), 0.0)
        self.assertEqual(clamp_curve_amount(9), 1.0)
        self.assertIsNone(clamp_curve_amount("nope"))
        self.assertEqual(normalize_curve_direction("DOWN"), "down")
        self.assertEqual(normalize_curve_direction("sideways"), "up")

    def test_arc_up_vs_down_control_point(self):
        up = build_arc_path_commands(200, 0.5, "up")
        down = build_arc_path_commands(200, 0.5, "down")
        self.assertIsNotNone(up)
        self.assertIsNotNone(down)
        self.assertEqual(up[0], ["M", 0.0, 0.0])
        self.assertEqual(up[1][0], "Q")
        self.assertLess(up[1][2], 0)  # control Y above baseline
        self.assertGreater(down[1][2], 0)
        self.assertAlmostEqual(abs(up[1][2]), 200 * 0.5 * CURVE_BULGE_FACTOR)
        self.assertIsNone(build_arc_path_commands(200, 0, "up"))
        self.assertIsNone(curve_path_d(200, 0, "up"))
        self.assertIn("Q", curve_path_d(100, 0.4, "up"))

    def test_multiline_rejected(self):
        self.assertTrue(is_multiline_text("a\nb"))
        self.assertFalse(is_multiline_text("single"))


class CurveApplyClearTests(unittest.TestCase):
    def test_apply_and_clear_preserve_identity_and_style(self):
        base = {
            "blytzId": "b1_curve",
            "blytzName": "Headline",
            "type": "IText",
            "text": "Curve me",
            "fontWeight": "bold",
            "fontStyle": "italic",
            "underline": True,
            "textAlign": "center",
            "charSpacing": 40,
            "lineHeight": 1.4,
            "width": 180,
        }
        curved = apply_curve_to_props(
            base, type_key="itext", amount=0.6, direction="up", width=180
        )
        self.assertIsNotNone(curved)
        self.assertEqual(curved["blytzId"], "b1_curve")
        self.assertEqual(curved["blytzName"], "Headline")
        self.assertEqual(curved["fontWeight"], "bold")
        self.assertEqual(curved["fontStyle"], "italic")
        self.assertTrue(curved["underline"])
        self.assertEqual(curved["textAlign"], "center")
        self.assertEqual(curved["charSpacing"], 40)
        self.assertEqual(curved["path"]["type"], "Path")
        self.assertFalse(curved["path"]["visible"])
        self.assertIsInstance(curved["path"]["path"], list)
        self.assertEqual(curved["blytzCurve"]["direction"], "up")
        self.assertAlmostEqual(curved["blytzCurve"]["amount"], 0.6)

        straight = clear_curve_from_props(curved)
        self.assertNotIn("path", straight)
        self.assertNotIn("blytzCurve", straight)
        self.assertEqual(straight["text"], "Curve me")
        self.assertEqual(straight["fontWeight"], "bold")

    def test_reject_non_text_and_multiline(self):
        self.assertIsNone(
            apply_curve_to_props({"type": "Rect"}, type_key="rect", amount=0.5)
        )
        self.assertIsNone(
            apply_curve_to_props(
                {"text": "a\nb", "width": 100},
                type_key="itext",
                amount=0.5,
            )
        )

    def test_amount_zero_clears(self):
        base = {
            "text": "Hi",
            "width": 80,
            "path": {"type": "Path", "path": [["M", 0, 0]]},
            "blytzCurve": make_blytz_curve(0.5, "down"),
        }
        out = apply_curve_to_props(base, type_key="textbox", amount=0)
        self.assertNotIn("path", out)
        self.assertNotIn("blytzCurve", out)


class NestedPathSafetyTests(unittest.TestCase):
    def test_accepts_itext_with_hidden_path(self):
        props = apply_curve_to_props(
            {
                "type": "IText",
                "text": "Hello",
                "blytzId": "c1",
                "blytzName": "Text",
                "width": 120,
            },
            type_key="itext",
            amount=0.4,
            direction="down",
        )
        self.assertTrue(scan_canvas_payload(_v1([props]))["ok"])

    def test_rejects_nested_non_path_type(self):
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(
                _v1(
                    [
                        {
                            "type": "IText",
                            "text": "x",
                            "path": {"type": "Image", "src": "data:image/png;base64,xx"},
                        }
                    ]
                )
            )

    def test_rejects_nested_path_with_objects(self):
        with self.assertRaises(CanvasSafetyError):
            scan_canvas_payload(
                _v1(
                    [
                        {
                            "type": "IText",
                            "text": "x",
                            "path": {
                                "type": "Path",
                                "path": [["M", 0, 0], ["L", 1, 1]],
                                "objects": [{"type": "Rect"}],
                            },
                        }
                    ]
                )
            )

    def test_standalone_path_geometry_array_still_accepted(self):
        self.assertTrue(
            scan_canvas_payload(
                _v1(
                    [
                        {
                            "type": "Path",
                            "path": [["M", 0, 0], ["L", 10, 10]],
                            "fill": "#111",
                        }
                    ]
                )
            )["ok"]
        )


class CurveSerializeChromeTests(unittest.TestCase):
    def test_serialize_props_include_blytz_curve(self):
        root = Path(__file__).resolve().parents[3]
        src = (root / "static" / "js" / "editor_canvas.js").read_text(encoding="utf-8")
        self.assertIn('"blytzCurve"', src)
        self.assertIn("function applyTextCurve", src)
        self.assertIn("function clearTextCurve", src)
        self.assertIn("function buildArcPathD", src)
        self.assertIn("function previewTextCurveOnObject", src)
        self.assertIn("Nested path objects cannot contain objects", src)


class CurvePropertiesUiTests(unittest.TestCase):
    def test_properties_curve_section_wiring(self):
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        css = (root / "static" / "css" / "responsive.css").read_text(encoding="utf-8")
        contract = (root / "static" / "js" / "editor_contract.js").read_text(
            encoding="utf-8"
        )
        canvas = (root / "static" / "js" / "editor_canvas.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('"textCurve"', props)
        self.assertIn("buildTextCurveControls", props)
        self.assertIn("discardCurvePreview", props)
        self.assertIn("data-curve-enable", props)
        self.assertIn("data-curve-amount", props)
        self.assertIn("data-curve-direction", props)
        self.assertIn("data-curve-apply", props)
        self.assertIn("data-curve-cancel", props)
        self.assertIn("applyTextCurve", props)
        self.assertIn("previewTextCurveOnObject", props)
        self.assertIn("amountPct / 100", props)
        self.assertIn('min: "0"', props)
        self.assertIn('max: "100"', props)
        self.assertIn(".editor-props-curve", css)
        # Save/submit must discard preview before serializing.
        self.assertIn("discardCurvePreview", contract)
        self.assertIn("preparePersistPayload", contract)
        # View switch must discard preview before snapshotting live canvas.
        self.assertLess(
            canvas.index("discardCurvePreview"),
            canvas.index("var liveSnap = snapshotLiveCanvas()"),
        )

    def test_curve_gating_helpers_present(self):
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("curveSupportsObject", props)
        self.assertIn("textHasMultipleLines", props)
        self.assertIn("single-line text only", props)
        self.assertIn("session.dirty", props)
        self.assertIn("isActiveSelection", props)
        self.assertIn("readCurveUiFromObject", props)

    def test_apply_is_single_commit_via_stage_b_api(self):
        """Apply restores baseline silently, then one applyTextCurve commit."""
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        handler = props[props.index("function runCurvePanelClick") :]
        self.assertIn("discardCurvePreview()", handler)
        self.assertIn("a.applyTextCurve(", handler)
        self.assertLess(
            handler.index("discardCurvePreview()"),
            handler.index("a.applyTextCurve("),
        )
        preview = props[
            props.index("function runCurvePreview") : props.index(
                "function buildTextCurveControls"
            )
        ]
        self.assertIn("previewTextCurveOnObject", preview)
        self.assertNotIn("applyTextCurve", preview)
        self.assertNotIn("commitEdit", preview)

    def test_cancel_discards_without_apply(self):
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        handler = props[props.index("function runCurvePanelClick") :]
        cancel_block = handler[
            handler.index("if (cancelBtn)") : handler.index("if (dirBtn)")
        ]
        self.assertIn("discardCurvePreview()", cancel_block)
        self.assertNotIn("applyTextCurve", cancel_block)

    def test_slider_pct_maps_to_api_amount(self):
        """UI stores 0–100; Stage B API receives 0–1."""
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("amount: session.draft.amountPct / 100", props)
        self.assertIn(
            "draft.enabled && draft.amountPct > 0 ? draft.amountPct / 100 : 0",
            props,
        )
        self.assertIn("Math.round(Math.max(0, Math.min(1, amount)) * 100)", props)
