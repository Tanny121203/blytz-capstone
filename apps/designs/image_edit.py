"""
Image editing helpers for Blytz editor (Stage E).

Mirrors static/js/editor_properties.js + editor_canvas.js image controls:
  effective width/height via Fabric scale (not source replacement)
  aspect lock / unlock
  rotation normalize + reset-to-zero (center preserved)
  opacity 0–1 (UI 0–100%)
  fit-within-canvas (uniform scale, not stretch-fill)
  center on logical canvas

Crop is intentionally not implemented here — see SYSTEM_ARCHITECTURE.md.
"""

from __future__ import annotations

from typing import Any


CANVAS_SIZE = 800.0
SIZE_MIN = 8.0
SIZE_MAX = 1600.0
OPACITY_MIN = 0.0
OPACITY_MAX = 1.0
ROTATION_MIN = 0.0
ROTATION_MAX = 359.0


def is_image_type_key(type_key: str | None) -> bool:
    return (type_key or "").lower().replace("-", "") == "image"


def reject_non_positive(value: Any) -> bool:
    """True when value is blank / non-finite / zero / negative (must not apply)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return True
    return not (n == n and n != float("inf") and n != float("-inf") and n > 0)


def clamp_size(value: Any, size_min: float = SIZE_MIN, size_max: float = SIZE_MAX) -> float | None:
    """
    Effective display size in canvas units.
    Rejects blank / non-finite / zero / negative; clamps into [size_min, size_max].
    """
    if reject_non_positive(value):
        return None
    n = float(value)
    return max(size_min, min(size_max, n))


def scale_for_width(
    native_w: float,
    native_h: float,
    target_w: float,
    *,
    keep_proportions: bool,
    current_scale_y: float = 1.0,
) -> dict[str, float] | None:
    """
    Fabric-style scale update when setting effective width.
    Preserves aspect when keep_proportions (scaleY := scaleX).
    """
    tw = clamp_size(target_w)
    if tw is None or not (native_w > 0 and native_h > 0):
        return None
    sx = tw / native_w
    sy = sx if keep_proportions else float(current_scale_y)
    return {
        "scaleX": sx,
        "scaleY": sy,
        "width": native_w * sx,
        "height": native_h * sy,
    }


def scale_for_height(
    native_w: float,
    native_h: float,
    target_h: float,
    *,
    keep_proportions: bool,
    current_scale_x: float = 1.0,
) -> dict[str, float] | None:
    th = clamp_size(target_h)
    if th is None or not (native_w > 0 and native_h > 0):
        return None
    sy = th / native_h
    sx = sy if keep_proportions else float(current_scale_x)
    return {
        "scaleX": sx,
        "scaleY": sy,
        "width": native_w * sx,
        "height": native_h * sy,
    }


def clamp_opacity(value: Any) -> float | None:
    """Accept 0–1 fraction or 0–100 percent; return Fabric opacity 0–1."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    if n > 1.0:
        n = n / 100.0
    return max(OPACITY_MIN, min(OPACITY_MAX, n))


def normalize_angle(degrees: Any) -> float | None:
    try:
        a = float(degrees)
    except (TypeError, ValueError):
        return None
    if a != a or a in (float("inf"), float("-inf")):
        return None
    n = ((a % 360.0) + 360.0) % 360.0
    if n > ROTATION_MAX:
        n = ROTATION_MAX
    return n


def reset_rotation_preserves_center(
    center_x: float, center_y: float, angle: Any
) -> dict[str, float] | None:
    """Reset angle to 0; center point unchanged (Fabric origin-agnostic contract)."""
    cur = normalize_angle(angle)
    if cur is None:
        return None
    return {"angle": 0.0, "centerX": float(center_x), "centerY": float(center_y)}


def fit_within_canvas(
    width: Any,
    height: Any,
    canvas_size: float = CANVAS_SIZE,
) -> dict[str, float] | None:
    """
    Uniform scale so the box fits inside canvas_size×canvas_size.
    Preserves aspect; never stretch-to-fill (independent X/Y scales).
    """
    try:
        w = float(width)
        h = float(height)
        c = float(canvas_size)
    except (TypeError, ValueError):
        return None
    if not (w > 0 and h > 0 and c > 0):
        return None
    factor = min(c / w, c / h)
    if factor != factor or factor <= 0:
        return None
    return {
        "width": w * factor,
        "height": h * factor,
        "factor": factor,
        "centerX": c / 2.0,
        "centerY": c / 2.0,
    }


def center_on_canvas(
    width: Any,
    height: Any,
    canvas_size: float = CANVAS_SIZE,
) -> dict[str, float] | None:
    """AABB top-left for a box centered on the logical canvas (left/top origin)."""
    try:
        w = float(width)
        h = float(height)
        c = float(canvas_size)
    except (TypeError, ValueError):
        return None
    if not (w > 0 and h > 0 and c > 0):
        return None
    return {
        "left": (c - w) / 2.0,
        "top": (c - h) / 2.0,
        "centerX": c / 2.0,
        "centerY": c / 2.0,
        "width": w,
        "height": h,
    }


def preserves_identity(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Image edits must not mint ids, rename layers, or replace src."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    return (
        before.get("blytzId") == after.get("blytzId")
        and before.get("blytzName") == after.get("blytzName")
        and before.get("src") == after.get("src")
    )


def image_controls_gated(
    type_key: str | None,
    *,
    locked: bool = False,
    multi: bool = False,
) -> bool:
    """True when image placement / dim controls may run."""
    return is_image_type_key(type_key) and not locked and not multi
