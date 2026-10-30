"""
Viewport zoom math for the Blytz editor (Option A: shared scene transform).

Must stay aligned with static/js/editor_canvas.js scene zoom helpers.
Logical 800×800 object coords are unchanged — zoom is CSS on #editor-artboard-scene.
Fabric viewportTransform stays identity; garment + artwork share one matrix.
"""

from __future__ import annotations

from typing import Any

ZOOM_MIN = 0.35
ZOOM_MAX = 4.0
ZOOM_STEP_FACTOR = 1.1
LOGICAL_SIZE = 800.0


def clamp_zoom(value: float, *, lo: float = ZOOM_MIN, hi: float = ZOOM_MAX) -> float:
    try:
        z = float(value)
    except (TypeError, ValueError):
        z = 1.0
    if z != z:  # NaN
        z = 1.0
    return min(hi, max(lo, z))


def next_zoom_step(
    current: float,
    direction: int,
    *,
    factor: float = ZOOM_STEP_FACTOR,
    lo: float = ZOOM_MIN,
    hi: float = ZOOM_MAX,
) -> float:
    """
    Multiplicative step: direction > 0 → ×factor, < 0 → ÷factor, 0 → unchanged.
    Result is clamped to [lo, hi].
    """
    z = clamp_zoom(current, lo=lo, hi=hi)
    if direction > 0:
        return clamp_zoom(z * factor, lo=lo, hi=hi)
    if direction < 0:
        return clamp_zoom(z / factor, lo=lo, hi=hi)
    return z


def zoom_percent_label(zoom: float) -> str:
    """Rounded percent label for chrome (e.g. 100%)."""
    z = clamp_zoom(zoom)
    return str(int(round(z * 100))) + "%"


def scene_zoom_to_point(
    scale: float,
    pan_x: float,
    pan_y: float,
    point_x: float,
    point_y: float,
    next_scale: float,
    *,
    lo: float = ZOOM_MIN,
    hi: float = ZOOM_MAX,
) -> dict[str, float]:
    """
    Zoom about a wrap-local point so that point stays fixed on screen.

    Scene CSS: translate(pan) scale(scale) with transform-origin 0 0.
    wrap_xy = scale * scene_xy + pan
    """
    s0 = clamp_zoom(scale, lo=lo, hi=hi)
    if s0 <= 0:
        s0 = 1.0
    s1 = clamp_zoom(next_scale, lo=lo, hi=hi)
    scene_x = (float(point_x) - float(pan_x)) / s0
    scene_y = (float(point_y) - float(pan_y)) / s0
    return {
        "scale": s1,
        "pan_x": float(point_x) - s1 * scene_x,
        "pan_y": float(point_y) - s1 * scene_y,
    }


def map_logical_through_scene(
    logical_x: float,
    logical_y: float,
    *,
    display_size: float,
    scale: float,
    pan_x: float,
    pan_y: float,
    logical_size: float = LOGICAL_SIZE,
) -> tuple[float, float]:
    """
    Logical canvas point → wrap-local CSS px after scene transform.
    Used for fabric and garment identically (shared scene matrix).
    """
    ls = float(logical_size) if float(logical_size) > 0 else LOGICAL_SIZE
    ds = float(display_size)
    css_x = float(logical_x) * (ds / ls)
    css_y = float(logical_y) * (ds / ls)
    s = clamp_zoom(scale)
    return (s * css_x + float(pan_x), s * css_y + float(pan_y))


def glued_layer_points(
    logical_x: float,
    logical_y: float,
    *,
    display_size: float,
    scale: float,
    pan_x: float,
    pan_y: float,
) -> dict[str, Any]:
    """
    Invariant helper: fabric and garment share one scene matrix → same wrap point.
    """
    pt = map_logical_through_scene(
        logical_x,
        logical_y,
        display_size=display_size,
        scale=scale,
        pan_x=pan_x,
        pan_y=pan_y,
    )
    return {
        "fabric": {"x": pt[0], "y": pt[1]},
        "garment": {"x": pt[0], "y": pt[1]},
        "shared_matrix": True,
    }


def identity_scene() -> dict[str, float]:
    return {"scale": 1.0, "pan_x": 0.0, "pan_y": 0.0}
