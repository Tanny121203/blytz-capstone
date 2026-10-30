"""
Load Stage O.1 print areas from static/garments/garments.json.

Printable = flat front/back body panel in the 800×800 editor mockup (not 3D wrap).
AI bounds use primary areas only (id front|back). Overflow UI may OR all areas
including jersey name/number sub-guides.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

PRIMARY_AREA_IDS = frozenset({"front", "back"})


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    path = base / "static" / "garments" / "garments.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def get_print_areas(garment_template: str, view_id: str) -> list[dict[str, Any]]:
    """Return catalog print areas for garment + view (may be empty)."""
    gid = (garment_template or "").strip().lower()
    view = "back" if (view_id or "").strip().lower() == "back" else "front"
    garment = _catalog().get(gid) or {}
    views = garment.get("views") if isinstance(garment, dict) else None
    if not isinstance(views, dict):
        return []
    view_def = views.get(view) or {}
    raw = view_def.get("printAreas") if isinstance(view_def, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
            w = float(item.get("w", item.get("width")))
            h = float(item.get("h", item.get("height")))
        except (TypeError, ValueError):
            continue
        if not (w > 0 and h > 0):
            continue
        out.append(
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )
    return out


def primary_print_areas(areas: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Authoritative AI / bounds panels: id front|back.

    If none match, fall back to the single largest area by w*h.
    """
    areas = [a for a in (areas or []) if isinstance(a, dict)]
    primary = [a for a in areas if a.get("id") in PRIMARY_AREA_IDS]
    if primary:
        return primary
    if not areas:
        return []
    return [max(areas, key=lambda a: float(a.get("w", 0)) * float(a.get("h", 0)))]
