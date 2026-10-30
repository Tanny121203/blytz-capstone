"""Focused Stage E tests: image dims, aspect, rotation, opacity, fit/center, gating."""

from __future__ import annotations

import unittest
from pathlib import Path

from apps.designs.image_edit import (
    CANVAS_SIZE,
    SIZE_MAX,
    SIZE_MIN,
    center_on_canvas,
    clamp_opacity,
    clamp_size,
    fit_within_canvas,
    image_controls_gated,
    is_image_type_key,
    normalize_angle,
    preserves_identity,
    reject_non_positive,
    reset_rotation_preserves_center,
    scale_for_height,
    scale_for_width,
)


ROOT = Path(__file__).resolve().parents[3]


class ImageTypeGateTests(unittest.TestCase):
    def test_image_accepted(self):
        self.assertTrue(is_image_type_key("image"))
        self.assertTrue(is_image_type_key("Image"))

    def test_non_image_rejected(self):
        for key in ("itext", "rect", "ellipse", "path", "activeselection", "textbox"):
            self.assertFalse(is_image_type_key(key))
            self.assertFalse(image_controls_gated(key))

    def test_locked_and_multi_gated(self):
        self.assertFalse(image_controls_gated("image", locked=True))
        self.assertFalse(image_controls_gated("image", multi=True))
        self.assertTrue(image_controls_gated("image", locked=False, multi=False))


class SizeAspectTests(unittest.TestCase):
    def test_reject_blank_zero_negative(self):
        self.assertTrue(reject_non_positive(""))
        self.assertTrue(reject_non_positive(None))
        self.assertTrue(reject_non_positive(0))
        self.assertTrue(reject_non_positive(-10))
        self.assertTrue(reject_non_positive(float("nan")))
        self.assertFalse(reject_non_positive(12))

    def test_clamp_size_bounds(self):
        self.assertIsNone(clamp_size(0))
        self.assertIsNone(clamp_size(-1))
        self.assertEqual(clamp_size(4), SIZE_MIN)
        self.assertEqual(clamp_size(2000), SIZE_MAX)
        self.assertEqual(clamp_size(400), 400.0)

    def test_aspect_lock_width_scales_height(self):
        out = scale_for_width(200, 100, 400, keep_proportions=True)
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out["scaleX"], 2.0)
        self.assertAlmostEqual(out["scaleY"], 2.0)
        self.assertAlmostEqual(out["width"], 400.0)
        self.assertAlmostEqual(out["height"], 200.0)

    def test_aspect_unlock_width_keeps_scale_y(self):
        out = scale_for_width(
            200, 100, 400, keep_proportions=False, current_scale_y=1.5
        )
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out["scaleX"], 2.0)
        self.assertAlmostEqual(out["scaleY"], 1.5)
        self.assertAlmostEqual(out["height"], 150.0)

    def test_aspect_lock_height(self):
        out = scale_for_height(200, 100, 50, keep_proportions=True)
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out["scaleY"], 0.5)
        self.assertAlmostEqual(out["scaleX"], 0.5)
        self.assertAlmostEqual(out["width"], 100.0)


class RotationOpacityTests(unittest.TestCase):
    def test_normalize_angle(self):
        self.assertEqual(normalize_angle(0), 0.0)
        self.assertEqual(normalize_angle(360), 0.0)
        self.assertEqual(normalize_angle(-90), 270.0)
        self.assertIsNone(normalize_angle("x"))
        self.assertIsNone(normalize_angle(float("nan")))

    def test_reset_rotation_keeps_center(self):
        out = reset_rotation_preserves_center(400, 410, 45)
        self.assertEqual(out["angle"], 0.0)
        self.assertEqual(out["centerX"], 400.0)
        self.assertEqual(out["centerY"], 410.0)

    def test_opacity_fraction_and_percent(self):
        self.assertAlmostEqual(clamp_opacity(0.4), 0.4)
        self.assertAlmostEqual(clamp_opacity(40), 0.4)
        self.assertEqual(clamp_opacity(0), 0.0)
        self.assertEqual(clamp_opacity(100), 1.0)
        self.assertEqual(clamp_opacity(150), 1.0)
        self.assertIsNone(clamp_opacity("nope"))


class FitCenterIdentityTests(unittest.TestCase):
    def test_fit_preserves_aspect_not_stretch(self):
        out = fit_within_canvas(400, 200, CANVAS_SIZE)
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out["width"], 800.0)
        self.assertAlmostEqual(out["height"], 400.0)
        self.assertAlmostEqual(out["width"] / out["height"], 2.0)
        self.assertAlmostEqual(out["centerX"], 400.0)
        self.assertAlmostEqual(out["centerY"], 400.0)

    def test_fit_tall_image(self):
        out = fit_within_canvas(100, 400, CANVAS_SIZE)
        self.assertAlmostEqual(out["height"], 800.0)
        self.assertAlmostEqual(out["width"], 200.0)

    def test_center_on_canvas(self):
        out = center_on_canvas(200, 100, CANVAS_SIZE)
        self.assertAlmostEqual(out["left"], 300.0)
        self.assertAlmostEqual(out["top"], 350.0)
        self.assertAlmostEqual(out["centerX"], 400.0)

    def test_preserves_id_name_src(self):
        before = {
            "blytzId": "img-1",
            "blytzName": "Logo",
            "src": "data:image/png;base64,xx",
            "opacity": 1,
        }
        after = dict(before)
        after["opacity"] = 0.5
        after["angle"] = 15
        self.assertTrue(preserves_identity(before, after))
        after_bad = dict(after)
        after_bad["blytzId"] = "other"
        self.assertFalse(preserves_identity(before, after_bad))


class SourceWiringTests(unittest.TestCase):
    def test_properties_registry_and_placement(self):
        props = (ROOT / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('image: [', props)
        self.assertIn('"imagePlacement"', props)
        self.assertIn("Aspect ratio locked", props)
        self.assertIn("data-image-place", props)
        self.assertIn("fitActiveWithinCanvas", props)
        self.assertIn("resetActiveRotation", props)
        self.assertIn("centerActiveImage", props)
        self.assertIn("unlock in Layers", props)
        self.assertIn("value <= 0", props)
        self.assertIn("editor-props-opacity-num", props)
        # Lock state must force Properties rebuild (not patch-only).
        self.assertIn(':L" + lockedBit', props)

    def test_canvas_exports_image_helpers(self):
        canvas = (ROOT / "static" / "js" / "editor_canvas.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function fitActiveWithinCanvas", canvas)
        self.assertIn("function resetActiveRotation", canvas)
        self.assertIn("function centerActiveImage", canvas)
        self.assertIn("fitActiveWithinCanvas: fitActiveWithinCanvas", canvas)
        self.assertIn('typeKey(obj) !== "image"', canvas)
        self.assertIn("isObjectLocked(obj)", canvas)
        # Fit must use uniform factor (not independent stretch).
        self.assertIn("Math.min(LOGICAL_SIZE / sw, LOGICAL_SIZE / sh)", canvas)

    def test_serialize_props_unchanged_for_images(self):
        canvas = (ROOT / "static" / "js" / "editor_canvas.js").read_text(
            encoding="utf-8"
        )
        ser = canvas[canvas.index("var SERIALIZE_PROPS") : canvas.index("var CURVE_AMOUNT_MIN")]
        for key in ("blytzId", "blytzName", "blytzLocked", "blytzCurve"):
            self.assertIn('"' + key + '"', ser)
        # No custom crop type / crop metadata prop added.
        self.assertNotIn("blytzCrop", ser)
        self.assertNotIn("cropPath", ser)

    def test_no_crop_ui_claimed(self):
        props = (ROOT / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("data-crop", props)
        self.assertIn('value: "fit"', props)
        self.assertNotIn('value: "crop"', props)


if __name__ == "__main__":
    unittest.main()
