"""Focused viewport zoom math tests (Option A shared scene transform)."""

from __future__ import annotations

import unittest

from apps.designs.canvas_zoom import (
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STEP_FACTOR,
    clamp_zoom,
    glued_layer_points,
    identity_scene,
    map_logical_through_scene,
    next_zoom_step,
    scene_zoom_to_point,
    zoom_percent_label,
)


class ClampZoomTests(unittest.TestCase):
    def test_clamp_bounds(self):
        self.assertAlmostEqual(clamp_zoom(0.1), ZOOM_MIN)
        self.assertAlmostEqual(clamp_zoom(10), ZOOM_MAX)
        self.assertAlmostEqual(clamp_zoom(1), 1.0)
        self.assertAlmostEqual(clamp_zoom("bad"), 1.0)


class StepZoomTests(unittest.TestCase):
    def test_multiplicative_steps(self):
        self.assertAlmostEqual(next_zoom_step(1.0, 1), ZOOM_STEP_FACTOR)
        self.assertAlmostEqual(next_zoom_step(1.0, -1), 1.0 / ZOOM_STEP_FACTOR)
        self.assertAlmostEqual(next_zoom_step(1.0, 0), 1.0)

    def test_steps_clamp_at_edges(self):
        self.assertAlmostEqual(next_zoom_step(ZOOM_MIN, -1), ZOOM_MIN)
        self.assertAlmostEqual(next_zoom_step(ZOOM_MAX, 1), ZOOM_MAX)


class LabelTests(unittest.TestCase):
    def test_percent_label(self):
        self.assertEqual(zoom_percent_label(1), "100%")
        self.assertEqual(zoom_percent_label(1.1), "110%")
        self.assertEqual(zoom_percent_label(ZOOM_MIN), "35%")


class SceneZoomToPointTests(unittest.TestCase):
    def test_point_stays_fixed(self):
        # Zoom 1→1.1 about (200, 150); that wrap point must stay fixed.
        before = scene_zoom_to_point(1.0, 0.0, 0.0, 200.0, 150.0, 1.0)
        self.assertAlmostEqual(before["scale"], 1.0)
        self.assertAlmostEqual(before["pan_x"], 0.0)

        after = scene_zoom_to_point(1.0, 0.0, 0.0, 200.0, 150.0, 1.1)
        # Scene point under cursor was (200, 150); after: 1.1*200 + pan_x = 200
        self.assertAlmostEqual(after["scale"], 1.1)
        self.assertAlmostEqual(after["pan_x"], 200.0 - 1.1 * 200.0)
        self.assertAlmostEqual(after["pan_y"], 150.0 - 1.1 * 150.0)
        # Reconstruct wrap position of old scene point
        sx, sy = 200.0, 150.0
        wrap_x = after["scale"] * sx + after["pan_x"]
        wrap_y = after["scale"] * sy + after["pan_y"]
        self.assertAlmostEqual(wrap_x, 200.0)
        self.assertAlmostEqual(wrap_y, 150.0)

    def test_reset_identity(self):
        ident = identity_scene()
        self.assertEqual(ident["scale"], 1.0)
        self.assertEqual(ident["pan_x"], 0.0)
        self.assertEqual(ident["pan_y"], 0.0)


class GluedInvariantTests(unittest.TestCase):
    def test_fabric_and_garment_share_matrix(self):
        """Shared scene matrix ⇒ same wrap point for fabric and garment layers."""
        display = 400.0
        scale = 1.1
        pan_x, pan_y = -20.0, 10.0
        logical = (400.0, 400.0)
        pts = glued_layer_points(
            logical[0],
            logical[1],
            display_size=display,
            scale=scale,
            pan_x=pan_x,
            pan_y=pan_y,
        )
        self.assertTrue(pts["shared_matrix"])
        self.assertAlmostEqual(pts["fabric"]["x"], pts["garment"]["x"])
        self.assertAlmostEqual(pts["fabric"]["y"], pts["garment"]["y"])

        expected = map_logical_through_scene(
            logical[0],
            logical[1],
            display_size=display,
            scale=scale,
            pan_x=pan_x,
            pan_y=pan_y,
        )
        self.assertAlmostEqual(pts["fabric"]["x"], expected[0])
        self.assertAlmostEqual(pts["fabric"]["y"], expected[1])

    def test_glued_after_zoom_to_point(self):
        display = 400.0
        # Start identity, zoom about center of display
        mid = display / 2
        next_state = scene_zoom_to_point(1.0, 0.0, 0.0, mid, mid, 1.1)
        before = glued_layer_points(
            400,
            400,
            display_size=display,
            scale=1.0,
            pan_x=0.0,
            pan_y=0.0,
        )
        after = glued_layer_points(
            400,
            400,
            display_size=display,
            scale=next_state["scale"],
            pan_x=next_state["pan_x"],
            pan_y=next_state["pan_y"],
        )
        self.assertAlmostEqual(after["fabric"]["x"], after["garment"]["x"])
        self.assertAlmostEqual(after["fabric"]["y"], after["garment"]["y"])
        # Center logical point is at display mid before zoom; stays fixed after.
        self.assertAlmostEqual(before["fabric"]["x"], mid)
        self.assertAlmostEqual(after["fabric"]["x"], mid)
        self.assertAlmostEqual(after["fabric"]["y"], mid)


if __name__ == "__main__":
    unittest.main()
