"""
Stage O / O.1 helpers: AI candidate validation, print bounds, image merge, rate limit.

Does not call Gemini; does not mutate Design rows.
"""

from __future__ import annotations

import copy
import json
import re
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache

from apps.designs.canvas_safety import CanvasSafetyError, validate_v1_envelope
from apps.designs.forms import MAX_CANVAS_JSON_BYTES
from apps.designs.print_area_check import artwork_overflows_print_areas
from apps.designs.print_areas_catalog import get_print_areas, primary_print_areas
from services.ai_design import AIDesignError

# Matches client BlytzEditor.validateCanvasJSON AI rules.
LOGICAL_SIZE = 800

AI_BOUNDS_MAX_RETRIES = 2  # extra Gemini attempts after first failure
# Soft AI overflow vs strict dashed guides (editor UI unchanged).
# Stage O.1.2: full flat panels already span most of the garment face; 40px
# (was 60) keeps soft bounds from treating nearly the whole 800×800 as free.
DEFAULT_AI_PRINT_OVERFLOW_MARGIN_PX = 40

_IMAGE_CLEAR_RE = re.compile(
    r"\b("
    r"remove\s+images?|delete\s+images?|clear\s+images?|replace\s+images?|"
    r"no\s+images?|clear\s+(the\s+)?canvas|start\s+over|blank\s+canvas|"
    r"wipe\s+(the\s+)?(design|canvas)"
    r")\b",
    re.I,
)

_DUAL_SIDE_RE = re.compile(
    r"\b("
    r"front\s*(and|&|/)\s*back|both\s+sides|matching\s+set|"
    r"front\s+and\s+back|full\s+kit|front\s*\+\s*back"
    r")\b",
    re.I,
)


class AISuggestValidationError(ValueError):
    """Raised when a candidate envelope fails schema/size/safety/bounds rules."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_reference_image(image: dict | None) -> dict | None:
    """
    Validate an incoming reference image. Raise AISuggestValidationError
    (existing class) with a user-readable message on failure.
    Return a normalized {"data": base64_str, "mime_type": mime_str}.
    Never write to disk. Never persist.
    """
    if image is None:
        return None  # caller uses `if reference_image:` so None is fine
    if not isinstance(image, dict):
        raise AISuggestValidationError("Reference image must be an object.")
    data = image.get("data")
    mime = image.get("mime_type")
    if not isinstance(data, str) or not data:
        raise AISuggestValidationError("Reference image data is missing.")
    if not isinstance(mime, str):
        raise AISuggestValidationError("Reference image mime_type is missing.")
    mime = mime.strip().lower()
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise AISuggestValidationError(
            "Reference image must be PNG, JPEG, or WebP."
        )
    # Base64 decode, bounded. Cap decoded bytes at 4 MB.
    MAX_BYTES = 4 * 1024 * 1024
    # Reject pre-decode if the base64 string is obviously too big
    # (base64 is ~4/3 of raw; allow 20% overhead)
    if len(data) > int(MAX_BYTES * 1.4):
        raise AISuggestValidationError(
            "Reference image is too large (max 4 MB)."
        )
    import base64
    try:
        raw = base64.b64decode(data, validate=True)
    except Exception:
        raise AISuggestValidationError("Reference image is not valid base64.")
    if len(raw) > MAX_BYTES:
        raise AISuggestValidationError(
            "Reference image is too large (max 4 MB)."
        )
    # Magic byte check
    if mime == "image/png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AISuggestValidationError("Reference image content is not PNG.")
    if mime == "image/jpeg" and not raw.startswith(b"\xff\xd8\xff"):
        raise AISuggestValidationError("Reference image content is not JPEG.")
    if mime == "image/webp" and not (
        raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"
    ):
        raise AISuggestValidationError("Reference image content is not WebP.")
    # Pillow verify + dimension cap
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(raw)) as im:
            im.verify()
        # Re-open because verify() closes the stream
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
            if w > 2048 or h > 2048:
                raise AISuggestValidationError(
                    "Reference image dimensions must be 2048x2048 or smaller."
                )
    except AISuggestValidationError:
        raise
    except Exception:
        raise AISuggestValidationError("Reference image is not a valid image.")
    return {"data": data, "mime_type": mime}


def _utf8_byte_length(value: str) -> int:
    return len(value.encode("utf-8"))


def wants_clear_images(message: str) -> bool:
    return bool(_IMAGE_CLEAR_RE.search(message or ""))


def should_generate_dual_side(garment_template: str, message: str) -> bool:
    gid = (garment_template or "").strip().lower()
    if gid == "jersey":
        return True
    return bool(_DUAL_SIDE_RE.search(message or ""))


def _is_image_obj(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    t = str(obj.get("type") or "").lower()
    return t in ("image", "fabricimage")


def extract_image_objects(canvas_json: dict[str, Any] | None) -> list[dict]:
    if not isinstance(canvas_json, dict):
        return []
    canvas = canvas_json.get("canvas")
    if not isinstance(canvas, dict):
        return []
    objs = canvas.get("objects")
    if not isinstance(objs, list):
        return []
    return [o for o in objs if _is_image_obj(o)]


def merge_preserve_images(
    envelope: dict[str, Any],
    prior_canvas: dict[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    """
    Soft-merge prior image objects into the AI candidate when omitted.

    Skipped when the user clearly asks to clear/replace images.
    """
    if wants_clear_images(message):
        return envelope
    prior_images = extract_image_objects(prior_canvas)
    if not prior_images:
        return envelope
    if not isinstance(envelope, dict):
        return envelope
    canvas = envelope.get("canvas")
    if not isinstance(canvas, dict):
        return envelope
    objs = list(canvas.get("objects") or [])
    if not isinstance(objs, list):
        objs = []

    def _key(img: dict) -> str:
        return str(
            img.get("blytzId")
            or img.get("id")
            or img.get("src")
            or ""
        )

    present = {_key(o) for o in objs if _is_image_obj(o)}
    for img in prior_images:
        k = _key(img)
        if k and k in present:
            continue
        # Also match by src alone.
        src = img.get("src")
        if src and any(
            _is_image_obj(o) and o.get("src") == src for o in objs
        ):
            continue
        objs.append(img)
        if k:
            present.add(k)
    canvas["objects"] = objs
    envelope["canvas"] = canvas
    return envelope


REDESIGN_CUES = (
    "redesign",
    "start over",
    "from scratch",
    "completely",
    "new design",
    "replace",
    "add ",
    "remove ",
    "delete ",
    "bigger",
    "smaller",
    "move ",
    "rotate",
    "resize",
    "scale",
    "make it bigger",
    "make it smaller",
)

COLOR_CUES = (
    "color",
    "colour",
    "colors",
    "colours",
    "palette",
    "shade",
    "tint",
    "red",
    "blue",
    "green",
    "yellow",
    "orange",
    "purple",
    "pink",
    "black",
    "white",
    "grey",
    "gray",
    "cyan",
    "magenta",
    "brown",
    "gold",
    "silver",
    "teal",
    "navy",
    "maroon",
    "olive",
    "lime",
    "violet",
    "indigo",
)

TEXT_CUES = (
    "change the text", "change text", "update the text", "update text",
    "rename the text", "rename text",
    "make it say", "make the text say", "make text say",
    "the text should be", "the text should say", "text should be", "text should say",
    "change the wording", "change wording",
    "replace the text", "replace text",
    "use this font", "use the font", "change the font",
    "font from", "font in", "typeface",
)

TEXT_PATCHABLE_PROPERTIES = frozenset({
    "text", "fontSize", "fontFamily", "fontWeight", "fontStyle", "fill", "stroke",
})
TEXT_OBJECT_TYPES = frozenset({"text", "IText", "textbox"})

ELEMENT_CUES = (
    "change the design in the middle",
    "replace the",
    "swap the",
    "change the logo",
    "change the center",
)

_HEX_COLOR_RE = re.compile(r"#[0-9a-f]{3,8}\b", re.I)


def detect_scope(message: str) -> str:
    msg = (message or "").lower()
    has_element = any(cue in msg for cue in ELEMENT_CUES)
    redesign_cues_to_check = [c for c in REDESIGN_CUES if c != "replace"] if has_element else REDESIGN_CUES
    for cue in redesign_cues_to_check:
        if cue in msg:
            return "redesign"
    if has_element:
        return "element"
    has_text = any(cue in msg for cue in TEXT_CUES)
    has_color = any(cue in msg for cue in COLOR_CUES) or bool(_HEX_COLOR_RE.search(msg))
    if has_text and has_color:
        return "redesign"
    if has_text:
        return "text"
    if has_color:
        return "color"
    return "redesign"


def apply_patches(canvas_json: dict, patches: list[dict]) -> dict:
    copied = copy.deepcopy(canvas_json)
    objs = copied.get("canvas", {}).get("objects", [])
    obj_map = {str(o.get("blytzId")): o for o in objs if o.get("blytzId") is not None}
    for p in patches or []:
        bid = str(p.get("blytzId"))
        if bid not in obj_map:
            raise ValueError(f"unknown blytzId: {bid}")
        target = obj_map[bid]
        target[p["property"]] = p["value"]
    return copied


def apply_element_patches(original_canvas: dict, patches: list[dict]) -> dict:
    copied = copy.deepcopy(original_canvas)
    canvas_obj = copied.setdefault("canvas", {})
    objs = canvas_obj.setdefault("objects", [])
    if not isinstance(objs, list):
        objs = []
        canvas_obj["objects"] = objs

    import uuid

    for p in patches or []:
        if not isinstance(p, dict):
            continue
        action = str(p.get("action") or "").lower()
        bid = p.get("blytzId")
        bid_str = str(bid) if bid is not None else None

        if action == "remove":
            if bid_str is None:
                raise ValueError("remove action requires blytzId")
            new_objs = [
                o for o in objs
                if str(o.get("blytzId")) != bid_str and str(o.get("id")) != bid_str
            ]
            if len(new_objs) == len(objs):
                raise ValueError(f"unknown blytzId for remove: {bid_str}")
            objs = new_objs
        elif action == "add":
            new_obj = p.get("object")
            if not isinstance(new_obj, dict):
                raise ValueError("add action requires object dictionary")
            obj_copy = copy.deepcopy(new_obj)
            if not obj_copy.get("blytzId") and not obj_copy.get("id"):
                obj_copy["blytzId"] = f"elem-{uuid.uuid4().hex[:8]}"
            objs.append(obj_copy)
        elif action == "replace":
            if bid_str is None:
                raise ValueError("replace action requires blytzId")
            new_obj = p.get("object")
            if not isinstance(new_obj, dict):
                raise ValueError("replace action requires object dictionary")
            found = False
            new_objs = []
            for o in objs:
                if str(o.get("blytzId")) == bid_str or str(o.get("id")) == bid_str:
                    found = True
                else:
                    new_objs.append(o)
            if not found:
                raise ValueError(f"unknown blytzId for replace: {bid_str}")
            obj_copy = copy.deepcopy(new_obj)
            if not obj_copy.get("blytzId") and not obj_copy.get("id"):
                obj_copy["blytzId"] = f"elem-{uuid.uuid4().hex[:8]}"
            new_objs.append(obj_copy)
            objs = new_objs
        else:
            raise ValueError(f"unknown patch action: {action}")

    canvas_obj["objects"] = objs
    copied["canvas"] = canvas_obj
    return copied


def validate_element_preservation(original_canvas: dict, patched_canvas: dict, patches: list[dict]) -> None:
    orig_objs = original_canvas.get("canvas", {}).get("objects", [])
    patched_objs = patched_canvas.get("canvas", {}).get("objects", [])

    orig_map = {str(o.get("blytzId") or o.get("id")): o for o in orig_objs if (o.get("blytzId") is not None or o.get("id") is not None)}
    patched_map = {str(o.get("blytzId") or o.get("id")): o for o in patched_objs if (o.get("blytzId") is not None or o.get("id") is not None)}

    targeted_bids = set()
    for p in patches or []:
        bid = p.get("blytzId")
        if bid is not None:
            targeted_bids.add(str(bid))

    for bid, o_obj in orig_map.items():
        if bid not in targeted_bids:
            if bid not in patched_map:
                raise ValueError(f"preservation: untargeted object {bid} was removed")
            p_obj = patched_map[bid]
            all_keys = set(o_obj.keys()) | set(p_obj.keys())
            for k in all_keys:
                if o_obj.get(k) != p_obj.get(k):
                    raise ValueError(f"preservation: untargeted object {bid} modified property {k}")

    for p in patches or []:
        action = str(p.get("action") or "").lower()
        bid = str(p.get("blytzId")) if p.get("blytzId") is not None else None
        if action in ("remove", "replace"):
            if bid not in orig_map:
                raise ValueError(f"patch references unknown blytzId: {bid}")
        if action == "remove":
            if bid in patched_map:
                raise ValueError(f"remove action failed to remove blytzId: {bid}")
        elif action == "replace":
            if bid in patched_map and patched_map[bid] == orig_map[bid]:
                raise ValueError(f"replace action failed to change blytzId: {bid}")


def validate_preservation(scope: str, original: dict, patched: dict, patches: list[dict]) -> None:
    if scope not in ("color", "text"):
        raise NotImplementedError(f"Unsupported scope for validation: {scope}")
    orig_objs = original.get("canvas", {}).get("objects", [])
    patched_objs = patched.get("canvas", {}).get("objects", [])

    orig_ids = {str(o.get("blytzId")) for o in orig_objs if o.get("blytzId") is not None}
    patched_ids = {str(o.get("blytzId")) for o in patched_objs if o.get("blytzId") is not None}

    if orig_ids != patched_ids:
        raise ValueError("preservation: object set changed")

    orig_map = {str(o.get("blytzId")): o for o in orig_objs if o.get("blytzId") is not None}
    patched_map = {str(o.get("blytzId")): o for o in patched_objs if o.get("blytzId") is not None}

    if scope == "color":
        structural_props = ("left", "top", "width", "height", "angle", "scaleX", "scaleY", "type", "text")
        for bid, p_obj in patched_map.items():
            o_obj = orig_map[bid]
            for prop in structural_props:
                if o_obj.get(prop) != p_obj.get(prop):
                    raise ValueError(f"preservation: structural property changed for blytzId={bid}")

            all_keys = set(o_obj.keys()) | set(p_obj.keys())
            diffs = [k for k in all_keys if o_obj.get(k) != p_obj.get(k)]
            for d in diffs:
                if d not in ("fill", "stroke"):
                    raise ValueError(f"preservation: non-color property changed for blytzId={bid}")

        for p in patches or []:
            bid = str(p.get("blytzId"))
            if bid not in orig_map:
                raise ValueError(f"patch references unknown blytzId: {bid}")

    elif scope == "text":
        structural_props = ("left", "top", "width", "height", "angle", "scaleX", "scaleY")
        targeted_ids = {str(p.get("blytzId")) for p in (patches or [])}

        for bid, p_obj in patched_map.items():
            o_obj = orig_map[bid]
            if o_obj.get("type") != p_obj.get("type"):
                raise ValueError(f"preservation: type changed for blytzId={bid}")

            for prop in structural_props:
                if o_obj.get(prop) != p_obj.get(prop):
                    raise ValueError(f"preservation: structural property changed for blytzId={bid}")

            if bid in targeted_ids:
                if str(o_obj.get("type", "")) not in TEXT_OBJECT_TYPES:
                    raise ValueError(f"preservation: non-text object targeted for blytzId={bid}")

            all_keys = set(o_obj.keys()) | set(p_obj.keys())
            diffs = [k for k in all_keys if o_obj.get(k) != p_obj.get(k)]

            if bid not in targeted_ids:
                if diffs:
                    raise ValueError(f"preservation: untargeted object changed for blytzId={bid}")
            else:
                for d in diffs:
                    if d not in TEXT_PATCHABLE_PROPERTIES:
                        raise ValueError(f"preservation: disallowed property changed for blytzId={bid}")

        for p in patches or []:
            bid = str(p.get("blytzId"))
            if bid not in orig_map:
                raise ValueError(f"patch references unknown blytzId: {bid}")


def finalize_scope_result(
    message: str, original_canvas_json: dict, raw_result: dict, *,
    garment_template: str = "tee", active_side: str = "front",
    print_areas: list | None = None,
) -> dict:
    scope = raw_result.get("scope")
    if scope == "redesign":
        return raw_result
    if scope in ("color", "text", "element"):
        candidates = raw_result.get("suggestions", [])
        for c in candidates:
            try:
                patches = c.get("patches", [])
                if scope == "element":
                    patched = apply_element_patches(original_canvas_json, patches)
                    validate_element_preservation(original_canvas_json, patched, patches)
                else:
                    patched = apply_patches(original_canvas_json, patches)
                    validate_preservation(scope, original_canvas_json, patched, patches)
                env = {
                    "schema_version": 1,
                    "width": 800,
                    "height": 800,
                    "canvas": patched["canvas"],
                }
                validated = validate_ai_candidate_envelope(env)
                assert_envelope_in_print_bounds(
                    validated,
                    garment_template=garment_template,
                    side=active_side,
                )
                c["canvasJSON"] = validated
                if "patches" in c:
                    del c["patches"]
            except (ValueError, KeyError, TypeError, NotImplementedError, AISuggestValidationError) as exc:
                raise AIDesignError(
                    code="ai_scope_violation",
                    message="AI returned a design that did not preserve the original. Please retry.",
                ) from exc

        return raw_result

    return raw_result


def fabric_object_aabb(obj: Any) -> dict[str, float] | None:
    """Approximate axis-aligned bounds from serialized Fabric object."""
    if not isinstance(obj, dict):
        return None
    try:
        left = float(obj.get("left") or 0)
        top = float(obj.get("top") or 0)
        scale_x = float(obj.get("scaleX") if obj.get("scaleX") is not None else 1)
        scale_y = float(obj.get("scaleY") if obj.get("scaleY") is not None else 1)
        width = float(obj.get("width") or 0) * scale_x
        height = float(obj.get("height") or 0) * scale_y
    except (TypeError, ValueError):
        return None
    if width == 0 and height == 0:
        # Points / degenerate — treat as tiny box at left/top.
        width = 1.0
        height = 1.0
    if width < 0:
        left += width
        width = abs(width)
    if height < 0:
        top += height
        height = abs(height)
    return {"left": left, "top": top, "width": width, "height": height}


def envelope_object_rects(envelope: dict[str, Any]) -> list[dict[str, float]]:
    canvas = envelope.get("canvas") if isinstance(envelope, dict) else None
    objs = canvas.get("objects") if isinstance(canvas, dict) else None
    if not isinstance(objs, list):
        return []
    rects: list[dict[str, float]] = []
    for obj in objs:
        r = fabric_object_aabb(obj)
        if r:
            rects.append(r)
    return rects


def ai_print_overflow_margin_px() -> float:
    raw = getattr(
        settings, "AI_PRINT_OVERFLOW_MARGIN_PX", DEFAULT_AI_PRINT_OVERFLOW_MARGIN_PX
    )
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return float(DEFAULT_AI_PRINT_OVERFLOW_MARGIN_PX)


def expand_print_areas_for_ai(
    areas: list[dict[str, Any]] | None,
    *,
    margin_px: float | None = None,
    canvas_size: float = LOGICAL_SIZE,
) -> list[dict[str, Any]]:
    """
    Inflate each print area by margin on every side, clamped to [0, canvas_size].

    Used only for AI candidate soft-bounds. Editor overflow warning must keep
    the unexpanded catalog rectangles.
    """
    if margin_px is None:
        margin_px = ai_print_overflow_margin_px()
    margin = max(0.0, float(margin_px))
    out: list[dict[str, Any]] = []
    for area in areas or []:
        if not isinstance(area, dict):
            continue
        try:
            x = float(area.get("x"))
            y = float(area.get("y"))
            w = float(area.get("w", area.get("width")))
            h = float(area.get("h", area.get("height")))
        except (TypeError, ValueError):
            continue
        if not (w > 0 and h > 0):
            continue
        x0 = max(0.0, x - margin)
        y0 = max(0.0, y - margin)
        x1 = min(float(canvas_size), x + w + margin)
        y1 = min(float(canvas_size), y + h + margin)
        nw = x1 - x0
        nh = y1 - y0
        if nw <= 0 or nh <= 0:
            continue
        expanded = dict(area)
        expanded.update({"x": x0, "y": y0, "w": nw, "h": nh})
        out.append(expanded)
    return out


def _rect_fully_outside_canvas(
    rect: dict[str, float], *, canvas_size: float = LOGICAL_SIZE
) -> bool:
    return (
        rect["left"] + rect["width"] <= 0
        or rect["top"] + rect["height"] <= 0
        or rect["left"] >= canvas_size
        or rect["top"] >= canvas_size
    )


def assert_envelope_in_print_bounds(
    envelope: dict[str, Any],
    *,
    garment_template: str,
    side: str,
) -> None:
    """
    Soft AI bounds: primary panel expanded by AI_PRINT_OVERFLOW_MARGIN_PX.

    Small overflow past the dashed guide is allowed (manual edit + UI warning).
    Far overflow past the soft box still fails. Objects fully off the 800×800
    canvas are always rejected.
    """
    areas = primary_print_areas(get_print_areas(garment_template, side))
    if not areas:
        raise AISuggestValidationError(
            "No printable region is defined for this garment side."
        )
    rects = envelope_object_rects(envelope)
    if not rects:
        # Empty design is allowed (user may only keep images merged later).
        return
    for r in rects:
        if _rect_fully_outside_canvas(r):
            raise AISuggestValidationError(
                "AI placed artwork completely outside the 800×800 canvas."
            )
    soft_areas = expand_print_areas_for_ai(areas)
    if artwork_overflows_print_areas(soft_areas, rects):
        a = areas[0]
        margin = ai_print_overflow_margin_px()
        raise AISuggestValidationError(
            "AI placed artwork too far outside the printable "
            f"{side} panel "
            f"(x={a['x']}, y={a['y']}, w={a['w']}, h={a['h']}; "
            f"allowed soft margin ±{margin:g}px)."
        )


def validate_ai_candidate_envelope(data: Any) -> dict:
    """
    Validate one active-view AI candidate (Blytz schema v1, no views key).

    Same size/safety rules as editor save path for v1; additionally rejects
    any ``views`` key (AI is active-side only).
    """
    if not isinstance(data, dict):
        raise AISuggestValidationError("Candidate canvas must be an object.")

    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if _utf8_byte_length(encoded) > MAX_CANVAS_JSON_BYTES:
        raise AISuggestValidationError(
            "A candidate exceeded the 2 MiB canvas size limit."
        )

    if data.get("schema_version") != 1:
        raise AISuggestValidationError(
            "Each candidate must use schema_version 1."
        )
    if "views" in data:
        raise AISuggestValidationError(
            "Candidates must not include a views key."
        )
    width = data.get("width")
    height = data.get("height")
    if width not in (None, LOGICAL_SIZE) or height not in (None, LOGICAL_SIZE):
        if width != LOGICAL_SIZE or height != LOGICAL_SIZE:
            raise AISuggestValidationError(
                "Candidates must use an 800×800 canvas."
            )

    canvas = data.get("canvas")
    if not isinstance(canvas, dict):
        raise AISuggestValidationError(
            "Each candidate must include a canvas payload."
        )
    if not isinstance(canvas.get("objects"), list):
        raise AISuggestValidationError(
            "Candidate canvas.objects must be an array."
        )

    try:
        validate_v1_envelope(data)
    except CanvasSafetyError as exc:
        raise AISuggestValidationError(
            "A candidate failed canvas safety checks."
        ) from exc

    return data


def validate_two_candidates(
    suggestions: list[dict],
    *,
    garment_template: str = "tee",
    active_side: str = "front",
    prior_canvas: dict | None = None,
    message: str = "",
    dual_side: bool = False,
) -> list[dict]:
    """Validate exactly two suggestions; any failure rejects the whole turn."""
    if not isinstance(suggestions, list) or len(suggestions) != 2:
        raise AISuggestValidationError(
            "AI must return exactly two valid candidates."
        )
    other_side = "back" if active_side == "front" else "front"
    out: list[dict] = []
    for i, sug in enumerate(suggestions):
        if not isinstance(sug, dict):
            raise AISuggestValidationError("A candidate was malformed.")
        canvas = sug.get("canvasJSON")
        validated = validate_ai_candidate_envelope(canvas)
        validated = merge_preserve_images(validated, prior_canvas, message)
        assert_envelope_in_print_bounds(
            validated,
            garment_template=garment_template,
            side=active_side,
        )
        item: dict[str, Any] = {
            "id": str(sug.get("id") or f"candidate-{i + 1}"),
            "label": str(sug.get("label") or f"Option {i + 1}")[:80],
            "description": str(sug.get("description") or "")[:240],
            "canvasJSON": validated,
        }
        other = sug.get("otherSideCanvasJSON") or sug.get("other_side_canvas_json")
        if dual_side:
            if not isinstance(other, dict):
                raise AISuggestValidationError(
                    "Dual-side candidates must include otherSideCanvasJSON."
                )
            other_v = validate_ai_candidate_envelope(other)
            assert_envelope_in_print_bounds(
                other_v,
                garment_template=garment_template,
                side=other_side,
            )
            item["otherSideCanvasJSON"] = other_v
            item["other_side"] = other_side
        elif isinstance(other, dict):
            # Tolerate extra field when dual_side false: validate if present.
            other_v = validate_ai_candidate_envelope(other)
            assert_envelope_in_print_bounds(
                other_v,
                garment_template=garment_template,
                side=other_side,
            )
            item["otherSideCanvasJSON"] = other_v
            item["other_side"] = other_side
        out.append(item)
    seen: set[str] = set()
    for i, item in enumerate(out):
        if item["id"] in seen:
            item["id"] = f"{item['id']}-{i}"
        seen.add(item["id"])
    return out


def rate_limit_max() -> int:
    return int(getattr(settings, "AI_SUGGEST_RATE_LIMIT_PER_HOUR", 5) or 5)


def rate_limit_window_seconds() -> int:
    return int(
        getattr(settings, "AI_SUGGEST_RATE_LIMIT_WINDOW_SECONDS", 3600) or 3600
    )


def _rate_cache_key(user_id: int) -> str:
    return f"blytz:ai_suggest:success:{user_id}"


def rate_limit_remaining(user_id: int) -> int:
    """How many successful AI calls remain in the current window."""
    key = _rate_cache_key(user_id)
    stamps = cache.get(key) or []
    now = time.time()
    window = rate_limit_window_seconds()
    fresh = [t for t in stamps if isinstance(t, (int, float)) and now - t < window]
    return max(0, rate_limit_max() - len(fresh))


def check_rate_limit(user_id: int) -> tuple[bool, int]:
    """
    Return (allowed, remaining_after_if_success).

    Does not record a call — call record_rate_limit_success after a 200.
    """
    remaining = rate_limit_remaining(user_id)
    return remaining > 0, max(0, remaining - 1)


def record_rate_limit_success(user_id: int) -> None:
    key = _rate_cache_key(user_id)
    now = time.time()
    window = rate_limit_window_seconds()
    stamps = cache.get(key) or []
    fresh = [t for t in stamps if isinstance(t, (int, float)) and now - t < window]
    fresh.append(now)
    cache.set(key, fresh, timeout=window)
