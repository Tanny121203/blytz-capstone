"""
Curved-text helpers for Blytz editor (Stage B prototype).

Mirrors static/js/editor_canvas.js text-curve geometry / metadata:
  - Native Fabric IText.path + hidden Path (quadratic arc)
  - blytzCurve: { amount, direction, version }
  - amount 0 / clear → straight text (no path, no metadata)
"""

from __future__ import annotations

from typing import Any


CURVE_AMOUNT_MIN = 0.0
CURVE_AMOUNT_MAX = 1.0
CURVE_DIRECTIONS = ("up", "down")
CURVE_META_VERSION = 1
# Max control-point bulge as a fraction of measured text width.
CURVE_BULGE_FACTOR = 0.45


def clamp_curve_amount(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return max(CURVE_AMOUNT_MIN, min(CURVE_AMOUNT_MAX, n))


def normalize_curve_direction(value: Any) -> str:
    v = str(value or "up").lower()
    return v if v in CURVE_DIRECTIONS else "up"


def is_multiline_text(text: Any) -> bool:
    return "\n" in str(text or "") or "\r" in str(text or "")


def build_arc_path_commands(
    width: float,
    amount: float,
    direction: str = "up",
) -> list[list[Any]] | None:
    """
    Quadratic arc spanning [0, width] on X.

    Fabric canvas Y grows downward:
      up   → control point above the baseline (negative Y)
      down → control point below the baseline (positive Y)
    Returns None when amount is effectively straight.
    """
    try:
        w = float(width)
        a = float(amount)
    except (TypeError, ValueError):
        return None
    if w <= 0 or a != a:
        return None
    a = max(CURVE_AMOUNT_MIN, min(CURVE_AMOUNT_MAX, a))
    if a < 0.001:
        return None
    bulge = a * w * CURVE_BULGE_FACTOR
    cy = bulge if normalize_curve_direction(direction) == "down" else -bulge
    return [
        ["M", 0.0, 0.0],
        ["Q", w / 2.0, cy, w, 0.0],
    ]


def curve_path_d(width: float, amount: float, direction: str = "up") -> str | None:
    cmds = build_arc_path_commands(width, amount, direction)
    if not cmds:
        return None
    # M x y Q cx cy x y
    m, q = cmds
    return f"M {m[1]} {m[2]} Q {q[1]} {q[2]} {q[3]} {q[4]}"


def make_blytz_curve(amount: Any, direction: Any = "up") -> dict[str, Any] | None:
    a = clamp_curve_amount(amount)
    if a is None or a < 0.001:
        return None
    return {
        "amount": a,
        "direction": normalize_curve_direction(direction),
        "version": CURVE_META_VERSION,
    }


def apply_curve_to_props(
    props: dict[str, Any],
    *,
    type_key: str,
    amount: Any,
    direction: Any = "up",
    width: float | None = None,
) -> dict[str, Any] | None:
    """
    Return updated object props for a single-line text type, or None if rejected.
    Embeds a nested Path dict suitable for Fabric serialization shape checks.
    """
    from apps.designs.text_format import is_text_type_key

    if not is_text_type_key(type_key):
        return None
    if is_multiline_text(props.get("text")):
        return None
    a = clamp_curve_amount(amount)
    if a is None:
        return None
    out = dict(props)
    if a < 0.001:
        out.pop("path", None)
        out.pop("blytzCurve", None)
        out.pop("pathSide", None)
        out.pop("pathStartOffset", None)
        out.pop("pathAlign", None)
        return out

    w = float(width) if width is not None else float(props.get("width") or 0)
    if w <= 0:
        w = max(float(props.get("fontSize") or 48) * max(len(str(props.get("text") or "")), 1) * 0.5, 1.0)
    cmds = build_arc_path_commands(w, a, direction)
    if cmds is None:
        return None
    meta = make_blytz_curve(a, direction)
    out["path"] = {
        "type": "Path",
        "visible": False,
        "path": cmds,
        "fill": "",
        "stroke": "",
        "strokeWidth": 1,
    }
    out["pathSide"] = "left"
    out["pathStartOffset"] = 0
    out["pathAlign"] = "center"
    out["blytzCurve"] = meta
    return out


def clear_curve_from_props(props: dict[str, Any]) -> dict[str, Any]:
    out = dict(props)
    out.pop("path", None)
    out.pop("blytzCurve", None)
    return out
