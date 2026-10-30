"""Focused tests: text formatting helpers + undo/redo chrome + style buttons."""

from __future__ import annotations

import unittest
from pathlib import Path

from apps.designs.text_format import (
    TEXT_ALIGN_VALUES,
    apply_text_format,
    clamp_char_spacing,
    clamp_line_height,
    fabric_char_advance_px,
    is_bold_weight,
    is_italic_style,
    is_text_type_key,
    is_underlined,
    normalize_font_style,
    normalize_font_weight,
    normalize_text_align,
    normalize_underline,
)


class TextTypeGateTests(unittest.TestCase):
    def test_text_types_accepted(self):
        for key in ("itext", "text", "textbox", "IText", "Textbox"):
            self.assertTrue(is_text_type_key(key))

    def test_non_text_rejected(self):
        for key in ("image", "rect", "ellipse", "path", "activeselection"):
            self.assertFalse(is_text_type_key(key))
            self.assertIsNone(
                apply_text_format(
                    {"fill": "#000"},
                    type_key=key,
                    font_weight="bold",
                    font_style="italic",
                    underline=True,
                )
            )


class FontWeightTests(unittest.TestCase):
    def test_bold_toggle(self):
        self.assertEqual(normalize_font_weight(True), "bold")
        self.assertEqual(normalize_font_weight("bold"), "bold")
        self.assertEqual(normalize_font_weight(700), "bold")
        self.assertEqual(normalize_font_weight(False), "normal")
        self.assertEqual(normalize_font_weight("normal"), "normal")
        self.assertTrue(is_bold_weight("bold"))
        self.assertFalse(is_bold_weight("normal"))


class FontStyleTests(unittest.TestCase):
    def test_italic_toggle(self):
        self.assertEqual(normalize_font_style("italic"), "italic")
        self.assertEqual(normalize_font_style("oblique"), "italic")
        self.assertEqual(normalize_font_style(True), "italic")
        self.assertEqual(normalize_font_style("normal"), "normal")
        self.assertEqual(normalize_font_style(False), "normal")
        self.assertTrue(is_italic_style("italic"))
        self.assertFalse(is_italic_style("normal"))


class UnderlineTests(unittest.TestCase):
    def test_underline_toggle(self):
        self.assertTrue(normalize_underline(True))
        self.assertTrue(normalize_underline(1))
        self.assertTrue(normalize_underline("true"))
        self.assertFalse(normalize_underline(False))
        self.assertFalse(normalize_underline(None))
        self.assertFalse(normalize_underline(0))
        self.assertTrue(is_underlined(True))
        self.assertFalse(is_underlined(False))


class TextAlignTests(unittest.TestCase):
    def test_left_center_right(self):
        self.assertEqual(set(TEXT_ALIGN_VALUES), {"left", "center", "right"})
        self.assertEqual(normalize_text_align("center"), "center")
        self.assertEqual(normalize_text_align("RIGHT"), "right")
        self.assertEqual(normalize_text_align("justify"), "left")


class SpacingTests(unittest.TestCase):
    def test_char_spacing_clamp_and_fabric_units(self):
        self.assertEqual(clamp_char_spacing(0), 0.0)
        self.assertEqual(clamp_char_spacing(9999), 800.0)
        self.assertEqual(clamp_char_spacing(-999), -200.0)
        # Fabric: fontSize * charSpacing / 1000
        self.assertAlmostEqual(fabric_char_advance_px(48, 1000), 48.0)
        self.assertAlmostEqual(fabric_char_advance_px(40, 100), 4.0)

    def test_line_height_clamp(self):
        self.assertEqual(clamp_line_height(1.16), 1.16)
        self.assertEqual(clamp_line_height(0.1), 0.8)
        self.assertEqual(clamp_line_height(9), 2.5)


class ApplyTextFormatPersistenceShapeTests(unittest.TestCase):
    def test_all_properties_round_trip_on_text(self):
        base = {
            "blytzId": "b1_txt",
            "blytzName": "Headline",
            "type": "IText",
            "text": "Hello",
            "fontWeight": "normal",
            "fontStyle": "normal",
            "underline": False,
            "textAlign": "left",
            "charSpacing": 0,
            "lineHeight": 1.16,
        }
        out = apply_text_format(
            base,
            type_key="itext",
            font_weight="bold",
            font_style="italic",
            underline=True,
            text_align="center",
            char_spacing=120,
            line_height=1.4,
        )
        self.assertIsNotNone(out)
        self.assertEqual(out["blytzId"], "b1_txt")
        self.assertEqual(out["blytzName"], "Headline")
        self.assertEqual(out["fontWeight"], "bold")
        self.assertEqual(out["fontStyle"], "italic")
        self.assertTrue(out["underline"])
        self.assertEqual(out["textAlign"], "center")
        self.assertEqual(out["charSpacing"], 120.0)
        self.assertEqual(out["lineHeight"], 1.4)

    def test_style_toggles_are_independent(self):
        base = {"fontWeight": "normal", "fontStyle": "normal", "underline": False}
        bold_only = apply_text_format(base, type_key="text", font_weight="bold")
        self.assertEqual(bold_only["fontWeight"], "bold")
        self.assertEqual(bold_only["fontStyle"], "normal")
        self.assertFalse(bold_only["underline"])

        italic_only = apply_text_format(base, type_key="text", font_style="italic")
        self.assertEqual(italic_only["fontWeight"], "normal")
        self.assertEqual(italic_only["fontStyle"], "italic")
        self.assertFalse(italic_only["underline"])

        under_only = apply_text_format(base, type_key="text", underline=True)
        self.assertEqual(under_only["fontWeight"], "normal")
        self.assertEqual(under_only["fontStyle"], "normal")
        self.assertTrue(under_only["underline"])

    def test_history_contract_no_view_field(self):
        out = apply_text_format(
            {"text": "A"},
            type_key="textbox",
            text_align="right",
            font_style="italic",
            underline=True,
        )
        self.assertNotIn("activeView", out)
        self.assertNotIn("view", out)


class StyleButtonChromeTests(unittest.TestCase):
    def test_style_toggle_buttons_in_properties_js(self):
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        css = (root / "static" / "css" / "responsive.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-text-style', props)
        self.assertIn('buildTextStyleControls', props)
        self.assertIn('toggleTextStyle', props)
        self.assertIn('"textStyle"', props)
        self.assertIn('fontStyle', props)
        self.assertIn('underline', props)
        self.assertIn("aria-pressed", props)
        # Bold is a toggle button, not a checkbox control.
        self.assertNotIn('type: "checkbox",\n          className: "editor-props-check",\n          "data-prop": "fontWeight"', props)
        self.assertIn(".editor-props-style-btn", css)
        self.assertIn(".editor-props-style-btn.is-italic", css)
        self.assertIn(".editor-props-style-btn.is-underline", css)
        # Alignment buttons preserved.
        self.assertIn("data-text-align", props)
        self.assertIn("Letter spacing", props)
        self.assertIn("Line spacing", props)

    def test_commit_edit_pathway_for_style_props(self):
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('commitField(\n        obj,\n        "fontWeight"', props)
        self.assertIn('commitField(\n        obj,\n        "fontStyle"', props)
        self.assertIn('commitField(obj, "underline"', props)
        self.assertIn("a.commitEdit(", props)


class UndoRedoChromeVisibilityTests(unittest.TestCase):
    def test_undo_redo_visible_on_desktop_css(self):
        root = Path(__file__).resolve().parents[3]
        css = (root / "static" / "css" / "responsive.css").read_text(
            encoding="utf-8"
        )
        html = (root / "templates" / "designs" / "editor.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-editor-undo', html)
        self.assertIn('data-editor-redo', html)
        # Base rule must show the group (not display:none).
        start = css.find(".editor-undo-redo {")
        self.assertGreaterEqual(start, 0)
        block = css[start : css.find("}", start)]
        self.assertIn("display: inline-flex", block)
        self.assertNotIn("display: none", block)

    def test_print_warning_overlay_still_absolute(self):
        root = Path(__file__).resolve().parents[3]
        html = (root / "templates" / "designs" / "editor.html").read_text(
            encoding="utf-8"
        )
        css = (root / "static" / "css" / "responsive.css").read_text(
            encoding="utf-8"
        )
        wrap = html.find('id="editor-canvas-wrap"')
        warn = html.find('id="editor-print-overflow-warning"')
        self.assertGreater(warn, wrap)
        block_start = css.find(".editor-print-overflow-warning {")
        block = css[block_start : css.find("}", block_start)]
        self.assertIn("position: absolute", block)
