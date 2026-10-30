"""
Focused Stage 2 tests: canvas/selection alignment, centering, and flip flags.

Mirrors static/js/editor_canvas.js helpers. Does not invent print-area geometry.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from apps.designs.align_flip import (
    ALIGN_DIRECTIONS,
    aabb_delta_align,
    align_rect_to_canvas,
    align_rects_to_selection,
    canvas_box,
    center_group_on_canvas,
    composition_rejects_locked,
    distribute_rects,
    flip_flags,
    union_aabb,
)


CANVAS = 800.0


class AlignToCanvasTests(unittest.TestCase):
    def test_all_six_directions(self):
        rect = {"left": 100, "top": 150, "width": 80, "height": 40}
        left = align_rect_to_canvas(rect, "left", canvas_size=CANVAS)
        self.assertAlmostEqual(left["left"], 0.0)
        self.assertAlmostEqual(left["top"], 150.0)

        right = align_rect_to_canvas(rect, "right", canvas_size=CANVAS)
        self.assertAlmostEqual(right["left"], CANVAS - 80)

        hcenter = align_rect_to_canvas(rect, "hcenter", canvas_size=CANVAS)
        self.assertAlmostEqual(hcenter["left"], (CANVAS - 80) / 2)

        top = align_rect_to_canvas(rect, "top", canvas_size=CANVAS)
        self.assertAlmostEqual(top["top"], 0.0)

        bottom = align_rect_to_canvas(rect, "bottom", canvas_size=CANVAS)
        self.assertAlmostEqual(bottom["top"], CANVAS - 40)

        vcenter = align_rect_to_canvas(rect, "vcenter", canvas_size=CANVAS)
        self.assertAlmostEqual(vcenter["top"], (CANVAS - 40) / 2)

    def test_directions_cover_registry(self):
        self.assertEqual(
            set(ALIGN_DIRECTIONS),
            {"left", "hcenter", "right", "top", "vcenter", "bottom"},
        )


class CanvasCenteringTests(unittest.TestCase):
    def test_horizontal_and_vertical_group_center(self):
        rects = [
            {"left": 10, "top": 20, "width": 40, "height": 30},
            {"left": 70, "top": 80, "width": 20, "height": 10},
        ]
        h = center_group_on_canvas(rects, "horizontal", canvas_size=CANVAS)
        box_h = union_aabb(h)
        self.assertIsNotNone(box_h)
        self.assertAlmostEqual(box_h["left"] + box_h["width"] / 2, CANVAS / 2)

        v = center_group_on_canvas(rects, "vertical", canvas_size=CANVAS)
        box_v = union_aabb(v)
        self.assertIsNotNone(box_v)
        self.assertAlmostEqual(box_v["top"] + box_v["height"] / 2, CANVAS / 2)

        both = center_group_on_canvas(rects, "both", canvas_size=CANVAS)
        box_b = union_aabb(both)
        self.assertAlmostEqual(box_b["left"] + box_b["width"] / 2, CANVAS / 2)
        self.assertAlmostEqual(box_b["top"] + box_b["height"] / 2, CANVAS / 2)

    def test_single_object_center_matches_align(self):
        rect = {"left": 50, "top": 60, "width": 100, "height": 50}
        centered = center_group_on_canvas([rect], "horizontal", canvas_size=CANVAS)[0]
        aligned = align_rect_to_canvas(rect, "hcenter", canvas_size=CANVAS)
        self.assertAlmostEqual(centered["left"], aligned["left"])


class MultiSelectionAlignTests(unittest.TestCase):
    def test_align_left_to_selection_bounds(self):
        rects = [
            {"left": 100, "top": 10, "width": 40, "height": 20},
            {"left": 200, "top": 50, "width": 30, "height": 40},
        ]
        out = align_rects_to_selection(rects, "left")
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["left"], 100.0)
        self.assertAlmostEqual(out[1]["left"], 100.0)
        # Vertical positions unchanged for horizontal align.
        self.assertAlmostEqual(out[0]["top"], 10.0)
        self.assertAlmostEqual(out[1]["top"], 50.0)

    def test_align_hcenter_and_bottom(self):
        rects = [
            {"left": 0, "top": 0, "width": 20, "height": 20},
            {"left": 80, "top": 40, "width": 40, "height": 10},
        ]
        mid = align_rects_to_selection(rects, "hcenter")
        box = union_aabb(rects)
        cx = box["left"] + box["width"] / 2
        self.assertAlmostEqual(mid[0]["left"] + mid[0]["width"] / 2, cx)
        self.assertAlmostEqual(mid[1]["left"] + mid[1]["width"] / 2, cx)

        bottom = align_rects_to_selection(rects, "bottom")
        bottom_edge = box["top"] + box["height"]
        self.assertAlmostEqual(bottom[0]["top"] + bottom[0]["height"], bottom_edge)
        self.assertAlmostEqual(bottom[1]["top"] + bottom[1]["height"], bottom_edge)

    def test_does_not_mutate_inputs(self):
        rects = [{"left": 10, "top": 10, "width": 5, "height": 5}]
        before = copy.deepcopy(rects)
        align_rects_to_selection(rects, "right")
        center_group_on_canvas(rects, "both")
        self.assertEqual(rects, before)


class FlipTests(unittest.TestCase):
    def test_horizontal_and_vertical_toggle(self):
        self.assertEqual(
            flip_flags(False, False, "horizontal"),
            {"flipX": True, "flipY": False},
        )
        self.assertEqual(
            flip_flags(True, False, "horizontal"),
            {"flipX": False, "flipY": False},
        )
        self.assertEqual(
            flip_flags(False, False, "vertical"),
            {"flipX": False, "flipY": True},
        )

    def test_flip_preserves_identity_contract(self):
        """
        Flip only toggles flipX/flipY. Callers must keep blytzId / blytzName.
        """
        obj = {
            "blytzId": "b1_abc",
            "blytzName": "Logo",
            "flipX": False,
            "flipY": False,
            "type": "Image",
        }
        flags = flip_flags(obj["flipX"], obj["flipY"], "horizontal")
        obj["flipX"] = flags["flipX"]
        obj["flipY"] = flags["flipY"]
        self.assertEqual(obj["blytzId"], "b1_abc")
        self.assertEqual(obj["blytzName"], "Logo")
        self.assertTrue(obj["flipX"])


class HistoryViewContractTests(unittest.TestCase):
    def test_align_helpers_do_not_encode_view_switch(self):
        """Geometry helpers have no view field — undo stack owns Front/Back."""
        d = aabb_delta_align(
            {"left": 0, "top": 0, "width": 10, "height": 10},
            "left",
            canvas_box(CANVAS),
        )
        self.assertEqual(set(d.keys()), {"dx", "dy"})


class DistributeTests(unittest.TestCase):
    """Stage F — equal edge gaps on transformed AABBs; first/last fixed."""

    def test_horizontal_equal_gaps_unequal_sizes(self):
        rects = [
            {"left": 0, "top": 10, "width": 40, "height": 20},
            {"left": 100, "top": 10, "width": 20, "height": 50},
            {"left": 200, "top": 10, "width": 80, "height": 10},
        ]
        out = distribute_rects(rects, "horizontal")
        self.assertEqual(len(out), 3)
        # First/last AABB edges unchanged.
        self.assertAlmostEqual(out[0]["left"], 0.0)
        self.assertAlmostEqual(out[2]["left"] + out[2]["width"], 280.0)
        gap01 = out[1]["left"] - (out[0]["left"] + out[0]["width"])
        gap12 = out[2]["left"] - (out[1]["left"] + out[1]["width"])
        self.assertAlmostEqual(gap01, gap12)
        # Vertical positions untouched.
        self.assertAlmostEqual(out[0]["top"], 10.0)
        self.assertAlmostEqual(out[1]["top"], 10.0)
        self.assertAlmostEqual(out[2]["top"], 10.0)

    def test_vertical_orders_by_top_edge(self):
        rects = [
            {"left": 5, "top": 200, "width": 10, "height": 30},
            {"left": 5, "top": 0, "width": 10, "height": 20},
            {"left": 5, "top": 80, "width": 10, "height": 40},
        ]
        out = distribute_rects(rects, "vertical")
        # Result order matches input order; positions follow sorted tops.
        by_top = sorted(out, key=lambda r: r["top"])
        self.assertAlmostEqual(by_top[0]["top"], 0.0)
        self.assertAlmostEqual(by_top[2]["top"] + by_top[2]["height"], 230.0)
        g01 = by_top[1]["top"] - (by_top[0]["top"] + by_top[0]["height"])
        g12 = by_top[2]["top"] - (by_top[1]["top"] + by_top[1]["height"])
        self.assertAlmostEqual(g01, g12)

    def test_requires_at_least_three(self):
        two = [
            {"left": 0, "top": 0, "width": 10, "height": 10},
            {"left": 40, "top": 0, "width": 10, "height": 10},
        ]
        self.assertEqual(distribute_rects(two, "horizontal"), [])
        self.assertEqual(distribute_rects([], "vertical"), [])

    def test_preserves_relative_input_order(self):
        rects = [
            {"left": 50, "top": 0, "width": 10, "height": 10},
            {"left": 0, "top": 0, "width": 10, "height": 10},
            {"left": 100, "top": 0, "width": 10, "height": 10},
        ]
        out = distribute_rects(rects, "horizontal")
        # Input[0] was middle by left; after distribute it stays index 0.
        self.assertEqual(len(out), 3)
        self.assertAlmostEqual(out[1]["left"], 0.0)  # leftmost stays
        self.assertAlmostEqual(out[2]["left"] + out[2]["width"], 110.0)

    def test_does_not_mutate_inputs(self):
        rects = [
            {"left": 0, "top": 0, "width": 10, "height": 10},
            {"left": 30, "top": 0, "width": 20, "height": 10},
            {"left": 80, "top": 0, "width": 10, "height": 10},
        ]
        before = copy.deepcopy(rects)
        distribute_rects(rects, "horizontal")
        self.assertEqual(rects, before)


class LockedCompositionPolicyTests(unittest.TestCase):
    def test_rejects_when_any_locked(self):
        self.assertTrue(composition_rejects_locked([False, True, False]))
        self.assertTrue(composition_rejects_locked([True]))
        self.assertFalse(composition_rejects_locked([False, False]))
        self.assertFalse(composition_rejects_locked([]))


class OverlayFixPreservedTests(unittest.TestCase):
    def test_print_warning_still_absolute_inside_wrap(self):
        root = Path(__file__).resolve().parents[3]
        html = (root / "templates" / "designs" / "editor.html").read_text(
            encoding="utf-8"
        )
        css = (root / "static" / "css" / "responsive.css").read_text(
            encoding="utf-8"
        )
        wrap_idx = html.find('id="editor-canvas-wrap"')
        warn_idx = html.find('id="editor-print-overflow-warning"')
        self.assertGreater(warn_idx, wrap_idx)
        block_start = css.find(".editor-print-overflow-warning {")
        block = css[block_start : css.find("}", block_start)]
        self.assertIn("position: absolute", block)


class StageFSourceContractTests(unittest.TestCase):
    """Lightweight presence checks — behavior covered by helpers + browser QA."""

    def test_canvas_exposes_distribute_and_locked_gate(self):
        root = Path(__file__).resolve().parents[3]
        js = (root / "static" / "js" / "editor_canvas.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function distributeActive", js)
        self.assertIn("function selectionHasLockedMembers", js)
        self.assertIn("function clearSelection", js)
        self.assertIn("distributeAabbDeltas", js)
        self.assertIn("duplicate-selection", js)
        self.assertIn("Unlock locked layers before aligning", js)

    def test_properties_has_distribute_controls(self):
        root = Path(__file__).resolve().parents[3]
        props = (root / "static" / "js" / "editor_properties.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-distribute-action", props)
        self.assertIn("Select at least 3 objects to distribute", props)
