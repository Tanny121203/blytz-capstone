"""
Shared canvas safety rules for Blytz schema_version 1 payloads.

Must stay identical to static/js/editor_canvas.js scanCanvasPayload —
keep both rule sets in sync.

Applied only when schema_version == 1. Non-v1 payloads stay opaque.
"""

from __future__ import annotations

from typing import Any

# Identical allowlist to client ALLOWED_OBJECT_TYPES (via typeKey).
ALLOWED_TYPE_KEYS = frozenset(
    {
        "rect",
        "ellipse",
        "circle",
        "line",
        "polygon",
        "path",
        "text",
        "itext",
        "textbox",
        "image",
    }
)

ALLOWED_IMAGE_SRC_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/webp;base64,",
)

URL_KEYS = frozenset({"src", "source", "url", "href", "xlink:href"})

MAX_DEPTH = 20


class CanvasSafetyError(ValueError):
    """Raised when a v1 canvas payload fails the shared safety scan."""

    def __init__(self, reason: str, path: str = ""):
        self.reason = reason
        self.path = path
        super().__init__(reason)


def type_key(value: Any) -> str:
    """Lowercase and strip non-letters — identical to BlytzCanvas.typeKey."""
    if isinstance(value, dict):
        raw = value.get("type")
    else:
        raw = value
    return "".join(ch for ch in str(raw or "").lower() if "a" <= ch <= "z")


def _data_url_ok(src: Any) -> bool:
    if not isinstance(src, str) or not src:
        return False
    lower = src.lower()
    return any(lower.startswith(prefix) for prefix in ALLOWED_IMAGE_SRC_PREFIXES)


def _fail(reason: str, path: str) -> None:
    raise CanvasSafetyError(reason, path)


def _scan_url_keys(node: Any, path: str, depth: int) -> None:
    if depth > MAX_DEPTH:
        _fail("Exceeded maximum nesting depth.", path)
    if node is None or not isinstance(node, (dict, list)):
        return
    if isinstance(node, list):
        for i, item in enumerate(node):
            _scan_url_keys(item, f"{path}[{i}]", depth + 1)
        return
    for key, val in node.items():
        if key == "text":
            continue
        key_lower = str(key).lower()
        if key in URL_KEYS or key_lower in URL_KEYS:
            if isinstance(val, str) and not _data_url_ok(val):
                _fail("External or unsafe image source is not allowed.", f"{path}.{key}")
        if isinstance(val, (dict, list)):
            _scan_url_keys(val, f"{path}.{key}", depth + 1)


def _scan_fabric_object(obj: Any, path: str, depth: int) -> None:
    if depth > MAX_DEPTH:
        _fail("Exceeded maximum nesting depth.", path)
    if not isinstance(obj, dict):
        _fail("Invalid canvas object.", path)
    tk = type_key(obj)
    if tk not in ALLOWED_TYPE_KEYS:
        _fail(
            f"Unsupported object type (“{obj.get('type', 'unknown')}”).",
            f"{path}.type",
        )
    fill = obj.get("fill")
    if isinstance(fill, dict) and "source" in fill:
        _fail("Pattern fills are not allowed.", f"{path}.fill")
    stroke = obj.get("stroke")
    if isinstance(stroke, dict) and "source" in stroke:
        _fail("Pattern strokes are not allowed.", f"{path}.stroke")
    if obj.get("backgroundImage") is not None:
        _fail("backgroundImage is not allowed.", f"{path}.backgroundImage")
    if obj.get("overlayImage") is not None:
        _fail("overlayImage is not allowed.", f"{path}.overlayImage")
    nested = obj.get("objects")
    if nested is not None:
        if not isinstance(nested, list):
            _fail("objects must be an array.", f"{path}.objects")
        for i, child in enumerate(nested):
            _scan_fabric_object(child, f"{path}.objects[{i}]", depth + 1)
    clip = obj.get("clipPath")
    if clip is not None:
        _scan_fabric_object(clip, f"{path}.clipPath", depth + 1)
    # Text-on-path: IText/Text/Textbox may nest a Fabric Path object under "path".
    # Standalone Path objects use "path" as a command array — leave those alone.
    nested_path = obj.get("path")
    if isinstance(nested_path, dict):
        if type_key(nested_path) != "path":
            _fail(
                "Unsupported nested path object "
                f"(“{nested_path.get('type', 'unknown')}”).",
                f"{path}.path.type",
            )
        if nested_path.get("objects") is not None:
            _fail("Nested path objects cannot contain objects.", f"{path}.path.objects")
        _scan_fabric_object(nested_path, f"{path}.path", depth + 1)
    _scan_url_keys(obj, path, depth)


def _scan_canvas_root(canvas: Any, path: str, depth: int) -> None:
    if depth > MAX_DEPTH:
        _fail("Exceeded maximum nesting depth.", path)
    if not isinstance(canvas, dict):
        _fail("Invalid canvas payload.", path)
    if canvas.get("backgroundImage") is not None:
        _fail("backgroundImage is not allowed.", f"{path}.backgroundImage")
    if canvas.get("overlayImage") is not None:
        _fail("overlayImage is not allowed.", f"{path}.overlayImage")
    objects = canvas.get("objects")
    if objects is not None:
        if not isinstance(objects, list):
            _fail("canvas.objects must be an array.", f"{path}.objects")
        for i, obj in enumerate(objects):
            _scan_fabric_object(obj, f"{path}.objects[{i}]", depth + 1)
    _scan_url_keys(canvas, path, depth)


def scan_canvas_payload(envelope_or_canvas: Any) -> dict:
    """
    Scan a Blytz v1 envelope or raw Fabric canvas.

    Returns {"ok": True} or raises CanvasSafetyError.
    For a non-raising API, use try/except or validate_v1_envelope().
    """
    if not isinstance(envelope_or_canvas, dict):
        _fail("Invalid payload.", "")

    if "schema_version" in envelope_or_canvas or "canvas" in envelope_or_canvas:
        canvas = envelope_or_canvas.get("canvas")
        if canvas is not None:
            _scan_canvas_root(canvas, "canvas", 0)
        views = envelope_or_canvas.get("views")
        if views is not None:
            if not isinstance(views, dict):
                _fail("Invalid views object.", "views")
            for vk, back in views.items():
                if vk == "front":
                    _fail("views.front is not allowed.", "views.front")
                if vk != "back":
                    _fail("Unknown views key.", f"views.{vk}")
                if not isinstance(back, dict):
                    _fail("Invalid views.back payload.", "views.back")
                if not isinstance(back.get("objects"), list):
                    _fail("views.back.objects must be an array.", "views.back.objects")
                _scan_canvas_root(back, "views.back", 0)
        return {"ok": True, "reason": "", "path": ""}

    _scan_canvas_root(envelope_or_canvas, "canvas", 0)
    return {"ok": True, "reason": "", "path": ""}


def validate_v1_envelope(data: dict) -> None:
    """
    Validate schema_version == 1 envelope in place.

    Raises CanvasSafetyError on failure. No-op for non-dict.
    Caller must only invoke when schema_version == 1.
    """
    scan_canvas_payload(data)
