"""
Focused UC-06 tests: print-panel slots, placement plan, clamp, skip locked/hidden.

Mirrors static/js/editor_canvas.js auto-layout helpers via apps.designs.auto_layout.
"""

from __future__ import annotations

import unittest

from apps.designs.auto_layout import (
    TEXT_GAP_PX,
    clamp_center_inside_panel,
    derive_slots,
    plan_auto_layout,
    scale_to_fit,
)


# Tee front primary panel (garments.json).
TEE_FRONT = {"x": 100, "y": 160, "w": 600, "h": 520}


class SlotMathTests(unittest.TestCase):
    def test_derive_slots_center_and_chests(self):
        slots = derive_slots(TEE_FRONT)
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertAlmostEqual(slots["center"]["cx"], 400.0)
        self.assertAlmostEqual(slots["center"]["cy"], 160 + 520 * 0.38)
        self.assertLess(slots["left_chest"]["cx"], slots["center"]["cx"])
        self.assertGreater(slots["right_chest"]["cx"], slots["center"]["cx"])
        self.assertAlmostEqual(
            slots["left_chest"]["cy"], slots["right_chest"]["cy"]
        )
        self.assertEqual(slots["panel"]["w"], 600.0)

    def test_derive_slots_rejects_bad_panel(self):
        self.assertIsNone(derive_slots(None))
        self.assertIsNone(derive_slots({"x": 0, "y": 0, "w": 0, "h": 100}))


class ScaleAndClampTests(unittest.TestCase):
    def test_scale_to_fit_uniform(self):
        # 200x100 into 100x100 → factor 0.5
        self.assertAlmostEqual(scale_to_fit(200, 100, 100, 100), 0.5)
        # already fits; allow upscale to fill
        self.assertAlmostEqual(scale_to_fit(50, 50, 100, 100), 2.0)
        self.assertAlmostEqual(
            scale_to_fit(50, 50, 100, 100, allow_upscale=False), 1.0
        )

    def test_clamp_keeps_aabb_inside(self):
        # Oversized object centered → clamped to panel center
        cx, cy = clamp_center_inside_panel(0, 0, 40, 20, TEE_FRONT)
        self.assertGreaterEqual(cx - 20, TEE_FRONT["x"] - 1e-6)
        self.assertLessEqual(cx + 20, TEE_FRONT["x"] + TEE_FRONT["w"] + 1e-6)
        self.assertGreaterEqual(cy - 10, TEE_FRONT["y"] - 1e-6)
        self.assertLessEqual(cy + 10, TEE_FRONT["y"] + TEE_FRONT["h"] + 1e-6)

        # Tiny object far left → pushed into panel
        cx2, cy2 = clamp_center_inside_panel(0, 400, 10, 10, TEE_FRONT)
        self.assertAlmostEqual(cx2, TEE_FRONT["x"] + 5)
        self.assertAlmostEqual(cy2, 400.0)


class PlanRulesTests(unittest.TestCase):
    def test_empty_canvas_noop(self):
        plan = plan_auto_layout([], TEE_FRONT)
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["reason"], "empty")
        self.assertEqual(plan["placements"], [])

    def test_no_panel(self):
        plan = plan_auto_layout(
            [{"id": "a", "kind": "image", "width": 100, "height": 80, "order": 0}],
            None,
        )
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["reason"], "no_panel")

    def test_first_image_center_second_left_chest(self):
        items = [
            {"id": "img1", "kind": "image", "width": 200, "height": 160, "order": 0},
            {"id": "img2", "kind": "image", "width": 80, "height": 80, "order": 1},
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["placements"]), 2)
        slots = derive_slots(TEE_FRONT)
        assert slots is not None
        self.assertAlmostEqual(plan["placements"][0]["cx"], slots["center"]["cx"])
        self.assertAlmostEqual(
            plan["placements"][1]["cx"], slots["left_chest"]["cx"]
        )

    def test_third_image_right_chest_extras_unmoved(self):
        items = [
            {"id": f"i{n}", "kind": "image", "width": 60, "height": 60, "order": n}
            for n in range(4)
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["placements"]), 3)
        self.assertEqual(plan["skipped_extra_images"], 1)
        self.assertIn("unmoved", plan["notes"])
        slots = derive_slots(TEE_FRONT)
        assert slots is not None
        self.assertAlmostEqual(
            plan["placements"][2]["cx"], slots["right_chest"]["cx"]
        )

    def test_text_under_primary_image_with_gap(self):
        items = [
            {"id": "img", "kind": "image", "width": 120, "height": 100, "order": 0},
            {"id": "t1", "kind": "text", "width": 80, "height": 20, "order": 1},
            {"id": "t2", "kind": "itext", "width": 60, "height": 18, "order": 2},
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["placements"]), 3)
        img = plan["placements"][0]
        t1 = plan["placements"][1]
        t2 = plan["placements"][2]
        img_bottom = img["cy"] + img["height"] / 2
        t1_top = t1["cy"] - t1["height"] / 2
        self.assertAlmostEqual(t1_top, img_bottom + TEXT_GAP_PX, places=4)
        self.assertGreater(t2["cy"], t1["cy"])

    def test_text_only_wordmark_then_stack(self):
        items = [
            {"id": "a", "kind": "text", "width": 200, "height": 40, "order": 0},
            {"id": "b", "kind": "textbox", "width": 100, "height": 24, "order": 1},
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["placements"]), 2)
        slots = derive_slots(TEE_FRONT)
        assert slots is not None
        self.assertAlmostEqual(plan["placements"][0]["cx"], slots["wordmark"]["cx"])
        self.assertGreater(
            plan["placements"][1]["cy"], plan["placements"][0]["cy"]
        )

    def test_locked_and_hidden_skipped(self):
        items = [
            {
                "id": "locked",
                "kind": "image",
                "width": 100,
                "height": 80,
                "order": 0,
                "blytzLocked": True,
            },
            {
                "id": "hidden",
                "kind": "image",
                "width": 100,
                "height": 80,
                "order": 1,
                "visible": False,
            },
            {"id": "ok", "kind": "image", "width": 100, "height": 80, "order": 2},
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["placements"]), 1)
        self.assertEqual(plan["placements"][0]["id"], "ok")
        slots = derive_slots(TEE_FRONT)
        assert slots is not None
        # sole movable image → center slot
        self.assertAlmostEqual(plan["placements"][0]["cx"], slots["center"]["cx"])

    def test_stable_order_by_canvas_index(self):
        # Higher order index is later in bottom→top; first image is lowest order.
        items = [
            {"id": "top", "kind": "image", "width": 50, "height": 50, "order": 2},
            {"id": "bot", "kind": "image", "width": 50, "height": 50, "order": 0},
            {"id": "mid", "kind": "image", "width": 50, "height": 50, "order": 1},
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        ids = [p["id"] for p in plan["placements"]]
        self.assertEqual(ids, ["bot", "mid", "top"])

    def test_placements_fit_inside_panel(self):
        items = [
            {"id": "big", "kind": "image", "width": 900, "height": 700, "order": 0},
            {"id": "txt", "kind": "text", "width": 400, "height": 80, "order": 1},
        ]
        plan = plan_auto_layout(items, TEE_FRONT)
        self.assertTrue(plan["ok"])
        for pl in plan["placements"]:
            left = pl["cx"] - pl["width"] / 2
            right = pl["cx"] + pl["width"] / 2
            top = pl["cy"] - pl["height"] / 2
            bottom = pl["cy"] + pl["height"] / 2
            self.assertGreaterEqual(left, TEE_FRONT["x"] - 1e-4)
            self.assertLessEqual(right, TEE_FRONT["x"] + TEE_FRONT["w"] + 1e-4)
            self.assertGreaterEqual(top, TEE_FRONT["y"] - 1e-4)
            self.assertLessEqual(bottom, TEE_FRONT["y"] + TEE_FRONT["h"] + 1e-4)


if __name__ == "__main__":
    unittest.main()
