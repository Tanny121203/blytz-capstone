"""Friendly summary of canvas_json_snapshot for staff order detail."""

from __future__ import annotations

from typing import Any


def _type_key(obj: dict) -> str:
    raw = obj.get("type")
    if not isinstance(raw, str):
        return ""
    return "".join(ch for ch in raw.lower() if ch.isalpha())


def _as_color(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            r, g, b = int(value[0]), int(value[1]), int(value[2])
            return f"rgb({r}, {g}, {b})"
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


def _summarize_objects(objects: Any) -> dict:
    texts: list[str] = []
    fonts: list[str] = []
    colors: list[str] = []
    images: list[str] = []
    seen_fonts: set[str] = set()
    seen_colors: set[str] = set()

    if not isinstance(objects, list):
        return {
            "texts": texts,
            "fonts": fonts,
            "colors": colors,
            "images": images,
        }

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        tk = _type_key(obj)
        fill = _as_color(obj.get("fill"))
        stroke = _as_color(obj.get("stroke"))

        if tk in {"text", "itext", "textbox"}:
            text = obj.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
            font = obj.get("fontFamily")
            if isinstance(font, str) and font.strip() and font not in seen_fonts:
                seen_fonts.add(font)
                fonts.append(font.strip())
            if fill and fill not in seen_colors:
                seen_colors.add(fill)
                colors.append(fill)
        elif tk == "image":
            name = obj.get("blytzName")
            if not isinstance(name, str) or not name.strip():
                name = "Uploaded image"
            images.append(name.strip())
        else:
            if fill and fill not in seen_colors:
                seen_colors.add(fill)
                colors.append(fill)
            if stroke and stroke not in seen_colors:
                seen_colors.add(stroke)
                colors.append(stroke)

    return {
        "texts": texts,
        "fonts": fonts,
        "colors": colors,
        "images": images,
    }


def _fabric_objects(payload: Any) -> list | None:
    if not isinstance(payload, dict):
        return None
    objects = payload.get("objects")
    if objects is None:
        return []
    if not isinstance(objects, list):
        return None
    return objects


def parse_design_details(snapshot: Any) -> dict:
    """
    Parse a canvas JSON snapshot into per-view design details.

    Returns:
      {
        "ok": bool,
        "error": str | None,
        "views": [{"id", "label", "texts", "fonts", "colors", "images"}, ...]
      }
    """
    if snapshot is None or snapshot == {}:
        return {
            "ok": False,
            "error": "No design snapshot was stored with this order.",
            "views": [],
        }
    if not isinstance(snapshot, dict):
        return {
            "ok": False,
            "error": "Design details could not be read.",
            "views": [],
        }

    try:
        views_out: list[dict] = []

        if snapshot.get("schema_version") == 1:
            front_objs = _fabric_objects(snapshot.get("canvas"))
            if front_objs is None:
                return {
                    "ok": False,
                    "error": "Design details could not be read.",
                    "views": [],
                }
            front = _summarize_objects(front_objs)
            front.update({"id": "front", "label": "Front"})
            views_out.append(front)

            back_payload = None
            views = snapshot.get("views")
            if isinstance(views, dict):
                back_payload = views.get("back")
            back_objs = _fabric_objects(back_payload) if back_payload is not None else []
            if back_objs is None:
                return {
                    "ok": False,
                    "error": "Design details could not be read.",
                    "views": [],
                }
            back = _summarize_objects(back_objs)
            back.update({"id": "back", "label": "Back"})
            views_out.append(back)
        elif isinstance(snapshot.get("objects"), list):
            # Legacy stub / flat Fabric JSON
            summary = _summarize_objects(snapshot.get("objects"))
            summary.update({"id": "front", "label": "Front"})
            views_out.append(summary)
        elif isinstance(snapshot.get("canvas"), dict):
            objs = _fabric_objects(snapshot.get("canvas"))
            if objs is None:
                return {
                    "ok": False,
                    "error": "Design details could not be read.",
                    "views": [],
                }
            summary = _summarize_objects(objs)
            summary.update({"id": "front", "label": "Front"})
            views_out.append(summary)
        else:
            return {
                "ok": False,
                "error": "Design details could not be read.",
                "views": [],
            }

        return {"ok": True, "error": None, "views": views_out}
    except Exception:
        return {
            "ok": False,
            "error": "Design details could not be read.",
            "views": [],
        }
