"""
Print-area overflow geometry for Blytz editor warnings.

Must stay identical to static/js/editor_canvas.js helpers:
  printAreaContainsRect, artworkOverflowsPrintAreas.

Coordinates are 800×800 canvas units from editor_garments.js / garments.json.
This module does not invent physical print sizes.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence


PRINT_OVERFLOW_EPS = 1e-6


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_area(area: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Accept {x,y,w,h} print-area dicts; reject non-positive size."""
    if not isinstance(area, Mapping):
        return None
    x = _num(area.get("x"))
    y = _num(area.get("y"))
    w = _num(area.get("w", area.get("width")))
    h = _num(area.get("h", area.get("height")))
    if not (w > 0 and h > 0):
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def normalize_rect(rect: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Accept Fabric-like {left,top,width,height} or {x,y,w,h}."""
    if not isinstance(rect, Mapping):
        return None
    if "left" in rect or "width" in rect:
        left = _num(rect.get("left"))
        top = _num(rect.get("top"))
        width = _num(rect.get("width"))
        height = _num(rect.get("height"))
    else:
        left = _num(rect.get("x"))
        top = _num(rect.get("y"))
        width = _num(rect.get("w", rect.get("width")))
        height = _num(rect.get("h", rect.get("height")))
    if not (width > 0 and height > 0):
        return None
    return {"left": left, "top": top, "width": width, "height": height}


def print_area_contains_rect(
    area: Mapping[str, Any] | None,
    rect: Mapping[str, Any] | None,
    *,
    eps: float = PRINT_OVERFLOW_EPS,
) -> bool:
    """
    True when rect is fully inside area (edges may touch).
    Axis-aligned boxes only — callers must pass transformed bounds
    (e.g. Fabric getBoundingRect) for rotated/scaled objects.
    """
    a = normalize_area(area)
    r = normalize_rect(rect)
    if not a or not r:
        return False
    return (
        r["left"] >= a["x"] - eps
        and r["top"] >= a["y"] - eps
        and r["left"] + r["width"] <= a["x"] + a["w"] + eps
        and r["top"] + r["height"] <= a["y"] + a["h"] + eps
    )


def artwork_overflows_print_areas(
    areas: Sequence[Mapping[str, Any]] | None,
    rects: Iterable[Mapping[str, Any]] | None,
    *,
    eps: float = PRINT_OVERFLOW_EPS,
) -> bool:
    """
    True when any artwork rect is not fully contained in at least one print area.

    Multiple print areas (e.g. chest + left-chest) are OR'd: fitting entirely
    inside any one area is enough. Empty areas → no overflow claim (caller
    should treat as undefined guides).
    """
    if not areas:
        return False
    normalized_areas = [a for a in (normalize_area(x) for x in areas) if a]
    if not normalized_areas:
        return False
    for rect in rects or ():
        r = normalize_rect(rect)
        if not r:
            continue
        if not any(
            print_area_contains_rect(area, r, eps=eps) for area in normalized_areas
        ):
            return True
    return False


def evaluate_print_overflow(
    areas_result: Mapping[str, Any] | None,
    rects: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """
    Mirror JS evaluatePrintOverflow return shape for tests.

    areas_result: {ok, areas, reason} from getPrintAreas.
    """
    areas_result = areas_result or {}
    if not areas_result.get("ok"):
        return {
            "overflow": False,
            "defined": False,
            "reason": areas_result.get("reason") or "no_print_areas",
            "count": 0,
        }
    areas = areas_result.get("areas") or []
    rect_list = [r for r in (normalize_rect(x) for x in (rects or ())) if r]
    overflow = artwork_overflows_print_areas(areas, rect_list)
    return {
        "overflow": overflow,
        "defined": True,
        "reason": "overflow" if overflow else "ok",
        "count": len(rect_list),
    }
