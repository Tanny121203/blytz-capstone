"""
Focused Stage 1 tests: print-area overflow geometry.

Mirrors static/js/editor_canvas.js helpers (printAreaContainsRect /
artworkOverflowsPrintAreas / evaluatePrintOverflow). Does not invent
physical print sizes — uses catalog-shaped {x,y,w,h} rectangles.
"""

from __future__ import annotations

import copy
import math
import unittest

from apps.designs.print_area_check import (
    artwork_overflows_print_areas,
    evaluate_print_overflow,
    print_area_contains_rect,
)


# Tee front primary panel (Stage O.1.2 full flat) — garments.json / editor_garments.js.
FRONT = {"id": "front", "name": "Front", "x": 100, "y": 160, "w": 600, "h": 520}
# Secondary guide shape for OR tests (not in live tee catalog; geometry only).
LEFT_CHEST = {
    "id": "left-chest",
    "name": "Left chest",
    "x": 432,
    "y": 250,
    "w": 80,
    "h": 80,
}
TEE_FRONT = [FRONT, LEFT_CHEST]
CHEST = FRONT  # alias for older test names


def _aabb_for_rotated_rect(cx, cy, w, h, angle_deg):
    """Axis-aligned bounds of a center-anchored rectangle after rotation."""
    rad = math.radians(angle_deg)
    cos_a = abs(math.cos(rad))
    sin_a = abs(math.sin(rad))
    bw = w * cos_a + h * sin_a
    bh = w * sin_a + h * cos_a
    return {
        "left": cx - bw / 2,
        "top": cy - bh / 2,
        "width": bw,
        "height": bh,
    }


class PrintAreaContainsRectTests(unittest.TestCase):
    def test_fully_inside(self):
        rect = {"left": 310, "top": 270, "width": 100, "height": 100}
        self.assertTrue(print_area_contains_rect(CHEST, rect))

    def test_outside(self):
        rect = {"left": 10, "top": 10, "width": 50, "height": 50}
        self.assertFalse(print_area_contains_rect(CHEST, rect))

    def test_boundary_touching_is_inside(self):
        # Edges flush with the print area (touching = allowed).
        rect = {
            "left": CHEST["x"],
            "top": CHEST["y"],
            "width": CHEST["w"],
            "height": CHEST["h"],
        }
        self.assertTrue(print_area_contains_rect(CHEST, rect))

    def test_one_pixel_past_edge_is_outside(self):
        rect = {
            "left": CHEST["x"] - 1,
            "top": CHEST["y"],
            "width": CHEST["w"],
            "height": CHEST["h"],
        }
        self.assertFalse(print_area_contains_rect(CHEST, rect))

    def test_rejects_non_positive_area(self):
        self.assertFalse(
            print_area_contains_rect(
                {"x": 0, "y": 0, "w": 0, "h": 10},
                {"left": 0, "top": 0, "width": 1, "height": 1},
            )
        )


class ArtworkOverflowPrintAreasTests(unittest.TestCase):
    def test_empty_areas_never_claims_overflow(self):
        rect = {"left": 0, "top": 0, "width": 10, "height": 10}
        self.assertFalse(artwork_overflows_print_areas([], [rect]))
        self.assertFalse(artwork_overflows_print_areas(None, [rect]))

    def test_inside_any_of_multiple_areas(self):
        # Fits left-chest only (OR across areas).
        rect = {"left": 440, "top": 260, "width": 40, "height": 40}
        self.assertFalse(artwork_overflows_print_areas(TEE_FRONT, [rect]))

    def test_outside_all_areas(self):
        rect = {"left": 10, "top": 10, "width": 40, "height": 40}
        self.assertTrue(artwork_overflows_print_areas(TEE_FRONT, [rect]))

    def test_rotated_scaled_aabb_outside(self):
        # Nearly fills front panel unrotated; 45° AABB expands past the print area.
        cx = FRONT["x"] + FRONT["w"] / 2
        cy = FRONT["y"] + FRONT["h"] / 2
        w, h = 580.0, 500.0
        inside = {
            "left": cx - w / 2,
            "top": cy - h / 2,
            "width": w,
            "height": h,
        }
        self.assertFalse(artwork_overflows_print_areas([FRONT], [inside]))
        # Rotated AABB (same shape Fabric getBoundingRect returns).
        rotated = _aabb_for_rotated_rect(cx, cy, w, h, 45)
        self.assertTrue(artwork_overflows_print_areas([FRONT], [rotated]))
        # Scale-up: centered box larger than the print area.
        scaled = {
            "left": cx - 320,
            "top": cy - 270,
            "width": 640,
            "height": 540,
        }
        self.assertTrue(artwork_overflows_print_areas([FRONT], [scaled]))

    def test_does_not_mutate_inputs(self):
        areas = copy.deepcopy(TEE_FRONT)
        rects = [{"left": 10, "top": 10, "width": 5, "height": 5}]
        before_areas = copy.deepcopy(areas)
        before_rects = copy.deepcopy(rects)
        artwork_overflows_print_areas(areas, rects)
        self.assertEqual(areas, before_areas)
        self.assertEqual(rects, before_rects)


class EvaluatePrintOverflowTests(unittest.TestCase):
    def test_undefined_print_areas_disables_warning(self):
        result = evaluate_print_overflow(
            {"ok": False, "areas": [], "reason": "no_print_areas"},
            [{"left": 0, "top": 0, "width": 10, "height": 10}],
        )
        self.assertFalse(result["overflow"])
        self.assertFalse(result["defined"])
        self.assertEqual(result["reason"], "no_print_areas")

    def test_unknown_garment_reason_passthrough(self):
        result = evaluate_print_overflow(
            {"ok": False, "areas": [], "reason": "unknown_garment"},
            [],
        )
        self.assertFalse(result["defined"])
        self.assertEqual(result["reason"], "unknown_garment")

    def test_defined_ok_and_overflow(self):
        areas_result = {"ok": True, "areas": TEE_FRONT, "reason": ""}
        inside = evaluate_print_overflow(
            areas_result,
            [{"left": 310, "top": 270, "width": 80, "height": 80}],
        )
        self.assertTrue(inside["defined"])
        self.assertFalse(inside["overflow"])
        self.assertEqual(inside["reason"], "ok")

        outside = evaluate_print_overflow(
            areas_result,
            [{"left": 0, "top": 0, "width": 40, "height": 40}],
        )
        self.assertTrue(outside["defined"])
        self.assertTrue(outside["overflow"])
        self.assertEqual(outside["reason"], "overflow")

    def test_warning_contract_does_not_alter_payload_shape(self):
        """
        Geometry helpers are side-effect free: serialized design data is
        independent of overflow evaluation (warning is DOM-only in the editor).
        """
        payload = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [
                    {
                        "type": "Rect",
                        "left": 0,
                        "top": 0,
                        "width": 50,
                        "height": 50,
                        "blytzId": "r1",
                    }
                ],
            },
            "views": {"back": {"version": "6.6.1", "objects": []}},
        }
        snapshot = copy.deepcopy(payload)
        evaluate_print_overflow(
            {"ok": True, "areas": TEE_FRONT, "reason": ""},
            [{"left": 0, "top": 0, "width": 50, "height": 50}],
        )
        self.assertEqual(payload, snapshot)
        # No warning / print-guide keys introduced into the envelope.
        self.assertNotIn("printOverflow", payload)
        self.assertNotIn("warning", payload["canvas"])


class PrintOverflowWarningLayoutRegressionTests(unittest.TestCase):
    """
    Warning show/hide must not reflow artboard sizing.
    Static contract: overlay is absolutely positioned inside the canvas wrap.
    """

    def test_warning_is_absolute_overlay_inside_wrap(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        html = (root / "templates" / "designs" / "editor.html").read_text(
            encoding="utf-8"
        )
        css = (root / "static" / "css" / "responsive.css").read_text(
            encoding="utf-8"
        )
        # Banner lives inside #editor-canvas-wrap (not a host flex sibling).
        wrap_idx = html.find('id="editor-canvas-wrap"')
        warn_idx = html.find('id="editor-print-overflow-warning"')
        caption_idx = html.find("Working canvas 800×800", warn_idx)
        self.assertGreater(wrap_idx, 0)
        self.assertGreater(warn_idx, wrap_idx)
        self.assertGreater(caption_idx, warn_idx)
        # Caption is outside the wrap; warning markup appears before the wrap closes.
        between = html[warn_idx:caption_idx]
        self.assertIn("</div>", between)
        # CSS block for the warning must declare absolute positioning.
        block_start = css.find(".editor-print-overflow-warning {")
        self.assertGreaterEqual(block_start, 0)
        block_end = css.find("}", block_start)
        block = css[block_start:block_end]
        self.assertIn("position: absolute", block)
        self.assertIn("pointer-events: none", block)

    def test_repeated_overflow_toggles_are_side_effect_free(self):
        """Simulate rapid in/out boundary crossings during vertical drag."""
        areas_result = {"ok": True, "areas": TEE_FRONT, "reason": ""}
        inside = [{"left": 310, "top": 270, "width": 80, "height": 80}]
        outside = [{"left": 10, "top": 10, "width": 40, "height": 40}]
        states = []
        for i in range(40):
            rects = outside if i % 2 else inside
            states.append(evaluate_print_overflow(areas_result, rects))
        self.assertEqual(states[0]["reason"], "ok")
        self.assertEqual(states[1]["reason"], "overflow")
        self.assertTrue(all(s["defined"] for s in states))
        # Geometry evaluation never invents dimensions or mutates catalog areas.
        self.assertEqual(TEE_FRONT[0]["w"], 600)
        self.assertEqual(TEE_FRONT[0]["h"], 520)
