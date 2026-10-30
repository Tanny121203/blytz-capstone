"""
Alignment / centering / flip geometry for Blytz editor Stage 2.

Must stay identical to static/js/editor_canvas.js helpers:
  aabbDeltaAlign, unionAabb, centerGroupDelta, flipPreservesIdentity.

Coordinates are logical canvas units (default 800×800). Alignment is to the
logical canvas or to a selection AABB — never to print-area guides.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence


ALIGN_DIRECTIONS = (
    "left",
    "hcenter",
    "right",
    "top",
    "vcenter",
    "bottom",
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_aabb(rect: Mapping[str, Any] | None) -> dict[str, float] | None:
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


def union_aabb(rects: Iterable[Mapping[str, Any]] | None) -> dict[str, float] | None:
    left = float("inf")
    top = float("inf")
    right = float("-inf")
    bottom = float("-inf")
    count = 0
    for raw in rects or ():
        r = normalize_aabb(raw)
        if not r:
            continue
        count += 1
        left = min(left, r["left"])
        top = min(top, r["top"])
        right = max(right, r["left"] + r["width"])
        bottom = max(bottom, r["top"] + r["height"])
    if count == 0:
        return None
    return {
        "left": left,
        "top": top,
        "width": right - left,
        "height": bottom - top,
    }


def aabb_delta_align(
    rect: Mapping[str, Any] | None,
    direction: str,
    box: Mapping[str, Any] | None,
) -> dict[str, float]:
    """
    Return {dx, dy} translating rect so it aligns to box on direction.
    Box is an AABB (canvas or selection). Edges may coincide exactly.
    """
    r = normalize_aabb(rect)
    b = normalize_aabb(box)
    if not r or not b or direction not in ALIGN_DIRECTIONS:
        return {"dx": 0.0, "dy": 0.0}
    dx = 0.0
    dy = 0.0
    if direction == "left":
        dx = b["left"] - r["left"]
    elif direction == "hcenter":
        dx = (b["left"] + b["width"] / 2.0) - (r["left"] + r["width"] / 2.0)
    elif direction == "right":
        dx = (b["left"] + b["width"]) - (r["left"] + r["width"])
    elif direction == "top":
        dy = b["top"] - r["top"]
    elif direction == "vcenter":
        dy = (b["top"] + b["height"] / 2.0) - (r["top"] + r["height"] / 2.0)
    elif direction == "bottom":
        dy = (b["top"] + b["height"]) - (r["top"] + r["height"])
    return {"dx": dx, "dy": dy}


def canvas_box(size: float = 800.0) -> dict[str, float]:
    return {"left": 0.0, "top": 0.0, "width": float(size), "height": float(size)}


def align_rect_to_canvas(
    rect: Mapping[str, Any],
    direction: str,
    *,
    canvas_size: float = 800.0,
) -> dict[str, float]:
    """New AABB origin after aligning rect to the logical canvas."""
    r = normalize_aabb(rect)
    if not r:
        return {"left": 0.0, "top": 0.0, "width": 0.0, "height": 0.0}
    d = aabb_delta_align(r, direction, canvas_box(canvas_size))
    return {
        "left": r["left"] + d["dx"],
        "top": r["top"] + d["dy"],
        "width": r["width"],
        "height": r["height"],
    }


def align_rects_to_selection(
    rects: Sequence[Mapping[str, Any]],
    direction: str,
) -> list[dict[str, float]]:
    """Align each rect to the union AABB of the selection (same six directions)."""
    normalized = [normalize_aabb(r) for r in rects]
    normalized = [r for r in normalized if r]
    box = union_aabb(normalized)
    if not box:
        return []
    out: list[dict[str, float]] = []
    for r in normalized:
        d = aabb_delta_align(r, direction, box)
        out.append(
            {
                "left": r["left"] + d["dx"],
                "top": r["top"] + d["dy"],
                "width": r["width"],
                "height": r["height"],
            }
        )
    return out


def center_group_on_canvas(
    rects: Sequence[Mapping[str, Any]],
    axis: str,
    *,
    canvas_size: float = 800.0,
) -> list[dict[str, float]]:
    """
    Translate all rects by the same delta so the selection AABB centers on
    the logical canvas along axis ('horizontal' | 'vertical' | 'both').
    """
    normalized = [normalize_aabb(r) for r in rects]
    normalized = [r for r in normalized if r]
    box = union_aabb(normalized)
    if not box:
        return []
    canvas = canvas_box(canvas_size)
    dx = 0.0
    dy = 0.0
    if axis in ("horizontal", "both"):
        dx = (canvas["width"] / 2.0) - (box["left"] + box["width"] / 2.0)
    if axis in ("vertical", "both"):
        dy = (canvas["height"] / 2.0) - (box["top"] + box["height"] / 2.0)
    return [
        {
            "left": r["left"] + dx,
            "top": r["top"] + dy,
            "width": r["width"],
            "height": r["height"],
        }
        for r in normalized
    ]


def flip_flags(flip_x: bool, flip_y: bool, axis: str) -> dict[str, bool]:
    """Toggle Fabric-style flipX / flipY; identity fields unchanged by caller."""
    if axis == "horizontal":
        return {"flipX": not flip_x, "flipY": flip_y}
    if axis == "vertical":
        return {"flipX": flip_x, "flipY": not flip_y}
    return {"flipX": flip_x, "flipY": flip_y}


# ---------------------------------------------------------------------------
# Stage F — distribute + locked composition policy
# ---------------------------------------------------------------------------
#
# Distribution rule (transformed AABBs, not raw left/top):
#   1. Normalize each rect to an AABB (width/height > 0).
#   2. Require n >= 3; otherwise return [] (caller treats as no-op).
#   3. Sort by AABB.left (horizontal) or AABB.top (vertical); ties keep
#      stable original index order.
#   4. Keep the first and last objects fixed (their AABB edge positions).
#   5. Equal gap between consecutive AABBs:
#        span = last_edge - first_edge
#        gap  = (span - sum(sizes)) / (n - 1)
#      Place intermediates so each next edge = prev_edge + prev_size + gap.
#   Unequal sizes are honored via AABB extents; gap is edge-to-edge, not
#   center-to-center. Negative gaps (overlapping) are allowed and still even.
#
# Locked-object policy (composition ops: align / distribute / center / flip):
#   REJECT the entire operation if any selected member is locked — no object
#   moves, no history entry. Never silently skip or mutate locked objects.
#   Twin enforced in static/js/editor_canvas.js (selectionHasLockedMembers).


def distribute_rects(
    rects: Sequence[Mapping[str, Any]],
    axis: str,
) -> list[dict[str, float]]:
    """
    Evenly distribute ≥3 AABBs along axis ('horizontal' | 'vertical').
    Returns new AABBs in the same order as the input list (not sorted order).
    Fewer than 3 valid rects → [].
    """
    if axis not in ("horizontal", "vertical"):
        return []
    indexed: list[tuple[int, dict[str, float]]] = []
    for i, raw in enumerate(rects or ()):
        r = normalize_aabb(raw)
        if r:
            indexed.append((i, r))
    n = len(indexed)
    if n < 3:
        return []

    horizontal = axis == "horizontal"
    # Sort key: primary edge, then original index for stability.
    indexed_sorted = sorted(
        indexed,
        key=lambda pair: (
            pair[1]["left"] if horizontal else pair[1]["top"],
            pair[0],
        ),
    )

    sizes = [
        (r["width"] if horizontal else r["height"]) for _, r in indexed_sorted
    ]
    first = indexed_sorted[0][1]
    last = indexed_sorted[-1][1]
    first_edge = first["left"] if horizontal else first["top"]
    last_edge = (
        (last["left"] + last["width"])
        if horizontal
        else (last["top"] + last["height"])
    )
    span = last_edge - first_edge
    gap = (span - sum(sizes)) / (n - 1)

    # Target origins in sorted order.
    targets: list[float] = [first_edge]
    cursor = first_edge + sizes[0] + gap
    for i in range(1, n - 1):
        targets.append(cursor)
        cursor = cursor + sizes[i] + gap
    targets.append(last["left"] if horizontal else last["top"])

    # Map back to input order (valid rects only; invalid inputs dropped).
    result_by_input: dict[int, dict[str, float]] = {}
    for sort_i, (orig_i, r) in enumerate(indexed_sorted):
        if horizontal:
            result_by_input[orig_i] = {
                "left": targets[sort_i],
                "top": r["top"],
                "width": r["width"],
                "height": r["height"],
            }
        else:
            result_by_input[orig_i] = {
                "left": r["left"],
                "top": targets[sort_i],
                "width": r["width"],
                "height": r["height"],
            }
    return [result_by_input[i] for i, _ in indexed]


def composition_rejects_locked(locked_flags: Sequence[bool]) -> bool:
    """True when the whole composition op must be rejected (any locked)."""
    return any(bool(f) for f in locked_flags or ())
