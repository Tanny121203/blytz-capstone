"""
UC-06 rule-based auto-layout geometry (deterministic).

Must stay aligned with static/js/editor_canvas.js auto-layout helpers.
Slots are derived from the primary print panel {x,y,w,h} — not 3D / silhouette paths.

Ordering: canvas bottom→top index (stable). Locked/hidden items are excluded
by the caller before planning (or filtered here via flags).
Images beyond the 3rd are left unmoved (not in the plan).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TEXT_GAP_PX = 16.0
TEXT_STACK_GAP_PX = 12.0
# Slot fractions of the primary panel.
CENTER_W_FRAC = 0.55
CENTER_H_FRAC = 0.42
CHEST_W_FRAC = 0.22
CHEST_H_FRAC = 0.22
CHEST_X_INSET = 0.06
CHEST_Y_INSET = 0.10
WORDMARK_W_FRAC = 0.70
WORDMARK_H_FRAC = 0.18


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_panel(panel: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(panel, Mapping):
        return None
    x = _num(panel.get("x", panel.get("left")))
    y = _num(panel.get("y", panel.get("top")))
    w = _num(panel.get("w", panel.get("width")))
    h = _num(panel.get("h", panel.get("height")))
    if not (w > 0 and h > 0):
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def derive_slots(panel: Mapping[str, Any] | None) -> dict[str, dict[str, float]] | None:
    """Named max-fit boxes inside the primary print panel."""
    p = normalize_panel(panel)
    if not p:
        return None
    cx = p["x"] + p["w"] / 2.0
    cy = p["y"] + p["h"] / 2.0
    center_w = p["w"] * CENTER_W_FRAC
    center_h = p["h"] * CENTER_H_FRAC
    chest_w = p["w"] * CHEST_W_FRAC
    chest_h = p["h"] * CHEST_H_FRAC
    left_cx = p["x"] + p["w"] * CHEST_X_INSET + chest_w / 2.0
    right_cx = p["x"] + p["w"] * (1.0 - CHEST_X_INSET) - chest_w / 2.0
    chest_cy = p["y"] + p["h"] * CHEST_Y_INSET + chest_h / 2.0
    word_w = p["w"] * WORDMARK_W_FRAC
    word_h = p["h"] * WORDMARK_H_FRAC
    return {
        "center": {
            "cx": cx,
            "cy": p["y"] + p["h"] * 0.38,
            "max_w": center_w,
            "max_h": center_h,
        },
        "left_chest": {
            "cx": left_cx,
            "cy": chest_cy,
            "max_w": chest_w,
            "max_h": chest_h,
        },
        "right_chest": {
            "cx": right_cx,
            "cy": chest_cy,
            "max_w": chest_w,
            "max_h": chest_h,
        },
        "wordmark": {
            "cx": cx,
            "cy": cy,
            "max_w": word_w,
            "max_h": word_h,
        },
        "panel": p,
    }


def scale_to_fit(
    width: float,
    height: float,
    max_w: float,
    max_h: float,
    *,
    allow_upscale: bool = True,
) -> float:
    """Uniform scale so (width,height) fits in max box. Never returns <= 0."""
    w = max(1e-6, float(width))
    h = max(1e-6, float(height))
    mw = max(1e-6, float(max_w))
    mh = max(1e-6, float(max_h))
    factor = min(mw / w, mh / h)
    if not allow_upscale:
        factor = min(1.0, factor)
    return factor if factor > 0 else 1e-6


def clamp_center_inside_panel(
    cx: float,
    cy: float,
    width: float,
    height: float,
    panel: Mapping[str, Any],
) -> tuple[float, float]:
    """Keep AABB centered at (cx,cy) inside panel when possible."""
    p = normalize_panel(panel)
    if not p:
        return cx, cy
    half_w = max(0.0, width / 2.0)
    half_h = max(0.0, height / 2.0)
    min_cx = p["x"] + half_w
    max_cx = p["x"] + p["w"] - half_w
    min_cy = p["y"] + half_h
    max_cy = p["y"] + p["h"] - half_h
    if min_cx > max_cx:
        cx = p["x"] + p["w"] / 2.0
    else:
        cx = min(max(cx, min_cx), max_cx)
    if min_cy > max_cy:
        cy = p["y"] + p["h"] / 2.0
    else:
        cy = min(max(cy, min_cy), max_cy)
    return cx, cy


def _is_image(kind: str) -> bool:
    return kind == "image"


def _is_text(kind: str) -> bool:
    return kind in ("text", "itext", "textbox")


def plan_auto_layout(
    items: Sequence[Mapping[str, Any]] | None,
    panel: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Plan placements for movable items.

    Each item: {
      id, kind, width, height,  # current AABB size
      locked?, visible?, order?  # order = canvas index ascending = bottom→top
    }

    Returns {
      ok: bool,
      reason: str,
      placements: [{id, cx, cy, width, height, scale_factor}],
      skipped_extra_images: int,
      notes: str,
    }
    scale_factor multiplies current scaleX/scaleY uniformly.
    """
    slots = derive_slots(panel)
    if not slots:
        return {
            "ok": False,
            "reason": "no_panel",
            "placements": [],
            "skipped_extra_images": 0,
            "notes": "",
        }

    movable: list[dict[str, Any]] = []
    for i, raw in enumerate(items or ()):
        if not isinstance(raw, Mapping):
            continue
        visible = raw.get("visible", True)
        if visible is False:
            continue
        if raw.get("locked") or raw.get("blytzLocked"):
            continue
        kind = str(raw.get("kind") or raw.get("type") or "").lower()
        if not (_is_image(kind) or _is_text(kind)):
            continue
        w = _num(raw.get("width"))
        h = _num(raw.get("height"))
        if not (w > 0 and h > 0):
            continue
        oid = raw.get("id")
        if oid is None or oid == "":
            oid = i
        movable.append(
            {
                "id": oid,
                "kind": "image" if _is_image(kind) else "text",
                "width": w,
                "height": h,
                "order": int(raw.get("order", i)),
            }
        )

    if not movable:
        return {
            "ok": False,
            "reason": "empty",
            "placements": [],
            "skipped_extra_images": 0,
            "notes": "",
        }

    movable.sort(key=lambda it: (it["order"], str(it["id"])))
    images = [it for it in movable if it["kind"] == "image"]
    texts = [it for it in movable if it["kind"] == "text"]
    placements: list[dict[str, Any]] = []
    panel_n = slots["panel"]
    notes = ""
    skipped_extra = max(0, len(images) - 3)

    primary_bottom = None
    primary_cx = slots["center"]["cx"]

    def place_in_slot(item: dict[str, Any], slot: dict[str, float]) -> dict[str, Any]:
        factor = scale_to_fit(
            item["width"],
            item["height"],
            slot["max_w"],
            slot["max_h"],
            allow_upscale=True,
        )
        nw = item["width"] * factor
        nh = item["height"] * factor
        cx, cy = clamp_center_inside_panel(
            slot["cx"], slot["cy"], nw, nh, panel_n
        )
        return {
            "id": item["id"],
            "cx": cx,
            "cy": cy,
            "width": nw,
            "height": nh,
            "scale_factor": factor,
        }

    if images:
        slots_for_images = ("center", "left_chest", "right_chest")
        for idx, img in enumerate(images[:3]):
            slot = slots[slots_for_images[idx]]
            pl = place_in_slot(img, slot)
            placements.append(pl)
            if idx == 0:
                primary_bottom = pl["cy"] + pl["height"] / 2.0
                primary_cx = pl["cx"]
        if skipped_extra:
            notes = f"{skipped_extra} extra image(s) left unmoved."
    elif texts:
        # Text-only: first as centered wordmark.
        first = texts[0]
        pl = place_in_slot(first, slots["wordmark"])
        placements.append(pl)
        primary_bottom = pl["cy"] + pl["height"] / 2.0
        primary_cx = pl["cx"]
        texts = texts[1:]

    # Remaining texts stacked below primary.
    if texts and primary_bottom is not None:
        cursor_top = primary_bottom + TEXT_GAP_PX
        for t in texts:
            factor = scale_to_fit(
                t["width"],
                t["height"],
                panel_n["w"] * 0.85,
                panel_n["h"] * 0.12,
                allow_upscale=True,
            )
            nw = t["width"] * factor
            nh = t["height"] * factor
            cy = cursor_top + nh / 2.0
            cx, cy = clamp_center_inside_panel(primary_cx, cy, nw, nh, panel_n)
            placements.append(
                {
                    "id": t["id"],
                    "cx": cx,
                    "cy": cy,
                    "width": nw,
                    "height": nh,
                    "scale_factor": factor,
                }
            )
            cursor_top = cy + nh / 2.0 + TEXT_STACK_GAP_PX

    if not placements:
        return {
            "ok": False,
            "reason": "empty",
            "placements": [],
            "skipped_extra_images": skipped_extra,
            "notes": notes,
        }

    return {
        "ok": True,
        "reason": "ok",
        "placements": placements,
        "skipped_extra_images": skipped_extra,
        "notes": notes,
    }
