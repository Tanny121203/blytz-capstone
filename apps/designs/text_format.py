"""
Text formatting helpers for Blytz editor (Stage text formatting).

Mirrors Fabric.js 6.6.1 / editor_properties.js:
  fontWeight → "bold" | "normal"
  fontStyle → "italic" | "normal"
  underline → bool
  textAlign → left | center | right
  charSpacing → 1/1000 em (Fabric _getWidthOfCharSpacing)
  lineHeight → line-box multiplier (Fabric default ~1.16)
"""

from __future__ import annotations

from typing import Any


TEXT_ALIGN_VALUES = ("left", "center", "right")
CHAR_SPACING_MIN = -200
CHAR_SPACING_MAX = 800
LINE_HEIGHT_MIN = 0.8
LINE_HEIGHT_MAX = 2.5


def is_text_type_key(type_key: str | None) -> bool:
    return (type_key or "").lower().replace("-", "") in {
        "itext",
        "text",
        "textbox",
    }


def normalize_text_align(value: Any) -> str:
    v = str(value or "left").lower()
    return v if v in TEXT_ALIGN_VALUES else "left"


def is_bold_weight(weight: Any) -> bool:
    if weight is True:
        return True
    if isinstance(weight, (int, float)):
        return float(weight) >= 600
    s = str(weight or "normal").lower()
    return s in {"bold", "700", "800", "900"}


def normalize_font_weight(value: Any) -> str:
    bold = value is True or value in ("bold", 700, "700")
    return "bold" if bold else "normal"


def is_italic_style(style: Any) -> bool:
    if style is True:
        return True
    s = str(style or "normal").lower()
    return s in {"italic", "oblique"}


def normalize_font_style(value: Any) -> str:
    return "italic" if is_italic_style(value) else "normal"


def is_underlined(value: Any) -> bool:
    if value is True or value == 1:
        return True
    if value is False or value is None or value == 0:
        return False
    s = str(value).lower()
    return s in {"true", "1", "yes", "on"}


def normalize_underline(value: Any) -> bool:
    return is_underlined(value)


def clamp_char_spacing(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return max(CHAR_SPACING_MIN, min(CHAR_SPACING_MAX, n))


def clamp_line_height(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return max(LINE_HEIGHT_MIN, min(LINE_HEIGHT_MAX, n))


def apply_text_format(
    props: dict[str, Any],
    *,
    type_key: str,
    font_weight: Any = None,
    font_style: Any = None,
    underline: Any = None,
    text_align: Any = None,
    char_spacing: Any = None,
    line_height: Any = None,
) -> dict[str, Any] | None:
    """
    Return updated props for a text object, or None if type is not text.
    Never mutates non-text objects (images/shapes rejected).
    """
    if not is_text_type_key(type_key):
        return None
    out = dict(props)
    if font_weight is not None:
        out["fontWeight"] = normalize_font_weight(font_weight)
    if font_style is not None:
        out["fontStyle"] = normalize_font_style(font_style)
    if underline is not None:
        out["underline"] = normalize_underline(underline)
    if text_align is not None:
        out["textAlign"] = normalize_text_align(text_align)
    if char_spacing is not None:
        cs = clamp_char_spacing(char_spacing)
        if cs is None:
            return None
        out["charSpacing"] = cs
    if line_height is not None:
        lh = clamp_line_height(line_height)
        if lh is None:
            return None
        out["lineHeight"] = lh
    return out


def fabric_char_advance_px(font_size: float, char_spacing: float) -> float:
    """Fabric: fontSize * charSpacing / 1000."""
    return float(font_size) * float(char_spacing) / 1000.0
