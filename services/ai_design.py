"""
Gemini wrapper for Blytz Stage O / O.1 — two Fabric-compatible design candidates.

Apps import this module; do not call the Gemini HTTP API from views directly.
Never log full prompts or canvas JSON.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

CANDIDATES_REQUIRED = 2


def _system_prompt(*, dual_side: bool) -> str:
    dual_block = ""
    if dual_side:
        dual_block = """
Dual-side mode is ON for this turn:
- canvasJSON = the ACTIVE side only (still no "views" key inside it).
- Also include otherSideCanvasJSON with the SAME envelope shape for the OTHER side.
- Both sides must stay inside their respective printable panels.
"""
    else:
        dual_block = """
Dual-side mode is OFF:
- Return only canvasJSON for the active side.
- Do not include otherSideCanvasJSON.
"""

    return f"""You are Blytz's apparel design assistant for a Fabric.js editor.

The customer message is a DESIGN INSTRUCTION, not literal canvas text.
Interpret what they want drawn (words, shapes, colors, layout). Never paste the
full user prompt into any text/IText/textbox. If they say 'Add a large red text
that says TEST', the text content must be exactly "TEST".

Apparel-only: refuse homework, code, NSFW, or unrelated chat. On refuse still
return exactly two candidates that safely leave the printable panel empty
(or minimal) and explain briefly in "message".

Return ONLY a single JSON object (no markdown fences) with this exact shape:
{{
  "message": "short assistant reply to the customer",
  "candidates": [
    {{
      "id": "candidate-a",
      "label": "short label",
      "description": "one-line description",
      "canvasJSON": {{
        "schema_version": 1,
        "width": 800,
        "height": 800,
        "canvas": {{
          "version": "6.6.1",
          "objects": [ /* Fabric objects */ ]
        }}
      }},
      "otherSideCanvasJSON": {{ /* only when dual-side mode is ON */ }}
    }},
    {{
      "id": "candidate-b",
      "label": "short label",
      "description": "one-line description",
      "canvasJSON": {{ /* same envelope shape */ }}
    }}
  ]
}}

{dual_block}

Hard rules:
- Exactly TWO candidates — never one, never three+.
- Each canvasJSON / otherSideCanvasJSON is ONE side only. Do NOT include a "views" key.
- schema_version must be 1; width and height must be 800.
- Allowed object types only: rect, ellipse, circle, line, polygon, path, text, IText, textbox, image.
- Images may use only data:image/png|jpeg|webp;base64 sources — never http(s) URLs.
- Prefer placing objects inside the printable panel rect(s) in the user JSON
  (fields x,y,w,h in 800×800 units). The printable region is the full flat
  front/back of the mockup including sleeve areas as drawn (not 3D wrap).
  Small overflow past the panel is acceptable; the customer can nudge objects
  manually (editor shows an overflow warning).
- Still keep artwork on the garment face — do not scatter objects across empty
  canvas corners far from the panel. Fill the panel appropriately; dense layouts OK.
- Preserve existing image objects from current_canvas unless the customer asked to
  remove/replace/clear images or start over.
- Do not invent external assets.
- Use explicit fill, fontSize, left, top. Prefer coordinates inside the print panel.
"""


class AIDesignError(Exception):
    """Domain error from the AI design helper (safe to surface a message)."""

    def __init__(self, message: str, *, code: str = "ai_error"):
        self.message = message
        self.code = code
        super().__init__(message)


def gemini_configured() -> bool:
    key = getattr(settings, "GEMINI_API_KEY", "") or ""
    return bool(str(key).strip())


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise AIDesignError("AI returned an empty response.", code="ai_empty")
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise AIDesignError(
                "AI response was not valid JSON.", code="ai_parse"
            ) from None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIDesignError(
                "AI response was not valid JSON.", code="ai_parse"
            ) from exc
    if not isinstance(data, dict):
        raise AIDesignError("AI response must be a JSON object.", code="ai_parse")
    return data


def _normalize_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates") or payload.get("suggestions")
    if not isinstance(candidates, list) or len(candidates) != CANDIDATES_REQUIRED:
        raise AIDesignError(
            "AI did not return exactly two design candidates.",
            code="ai_candidates",
        )
    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise AIDesignError(
                "AI candidates were malformed.", code="ai_candidates"
            )
        canvas = item.get("canvasJSON") or item.get("canvas_json") or item.get("canvas")
        if not isinstance(canvas, dict):
            raise AIDesignError(
                "A candidate was missing canvas JSON.", code="ai_candidates"
            )
        cid = str(item.get("id") or f"candidate-{i + 1}")
        entry: dict[str, Any] = {
            "id": cid,
            "label": str(item.get("label") or f"Option {i + 1}")[:80],
            "description": str(item.get("description") or "")[:240],
            "canvasJSON": canvas,
        }
        other = item.get("otherSideCanvasJSON") or item.get("other_side_canvas_json")
        if isinstance(other, dict):
            entry["otherSideCanvasJSON"] = other
        normalized.append(entry)
    return normalized


def suggest_design_candidates(
    *,
    message: str,
    canvas_json: dict[str, Any] | None,
    active_side: str,
    garment_template: str = "tee",
    garment_color: str = "",
    print_areas: list[dict[str, Any]] | None = None,
    other_side_print_areas: list[dict[str, Any]] | None = None,
    dual_side: bool = False,
    repair_hint: str | None = None,
) -> dict[str, Any]:
    """
    Call Gemini and return {message, suggestions, usage, dual_side}.

    Raises AIDesignError on configuration / transport / parse failures.
    Does not validate canvas schema (caller must).
    """
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise AIDesignError(
            "AI suggestions are unavailable (no API key configured).",
            code="ai_unavailable",
        )

    model = (
        getattr(settings, "GEMINI_MODEL", "") or "gemini-3.5-flash-lite"
    ).strip() or "gemini-3.5-flash-lite"
    side = active_side if active_side in ("front", "back") else "front"
    other_side = "back" if side == "front" else "front"
    user_payload: dict[str, Any] = {
        "message": (message or "").strip(),
        "active_side": side,
        "garment_template": (garment_template or "tee").strip().lower(),
        "garment_color": (garment_color or "").strip().lower(),
        "canvas": {"width": 800, "height": 800},
        "print_areas": print_areas or [],
        "current_canvas": canvas_json if isinstance(canvas_json, dict) else {},
        "dual_side": bool(dual_side),
    }
    if dual_side:
        user_payload["other_side"] = other_side
        user_payload["other_side_print_areas"] = other_side_print_areas or []
    if repair_hint:
        user_payload["repair_hint"] = str(repair_hint)[:500]

    body = {
        "systemInstruction": {"parts": [{"text": _system_prompt(dual_side=dual_side)}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Customer request and structured garment/print context "
                            "(JSON). Prefer print_areas; slight overflow OK.\n"
                            + json.dumps(user_payload, ensure_ascii=False)
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        status_code = getattr(exc, "code", "?")
        reason = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:400]
            err_json = json.loads(err_body)
            err_obj = err_json.get("error") if isinstance(err_json, dict) else None
            if isinstance(err_obj, dict):
                reason = str(err_obj.get("status") or err_obj.get("message") or "")[
                    :120
                ]
            elif err_body:
                reason = err_body[:80].replace("\n", " ")
        except Exception:
            reason = ""
        logger.warning(
            "ai_suggest gemini_http_error status=%s model=%s reason=%s",
            status_code,
            model,
            reason,
        )
        if status_code in (401, 403):
            raise AIDesignError(
                "AI suggestions are unavailable (API key rejected).",
                code="ai_unavailable",
            ) from exc
        raise AIDesignError(
            "AI service request failed. Please try again.",
            code="ai_upstream",
        ) from exc
    except urllib.error.URLError as exc:
        logger.warning("ai_suggest gemini_network_error")
        raise AIDesignError(
            "AI service is unreachable. Please try again later.",
            code="ai_upstream",
        ) from exc

    if status >= 400:
        logger.warning("ai_suggest gemini_bad_status status=%s", status)
        raise AIDesignError(
            "AI service request failed. Please try again.",
            code="ai_upstream",
        )

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIDesignError(
            "AI service returned an unreadable response.", code="ai_parse"
        ) from exc

    usage = envelope.get("usageMetadata") or {}
    prompt_tokens = usage.get("promptTokenCount")
    output_tokens = usage.get("candidatesTokenCount") or usage.get(
        "totalTokenCount"
    )

    try:
        parts = (
            envelope.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        text = "".join(
            str(p.get("text") or "") for p in parts if isinstance(p, dict)
        )
    except (IndexError, AttributeError, TypeError) as exc:
        raise AIDesignError(
            "AI service returned an unexpected shape.", code="ai_parse"
        ) from exc

    parsed = _extract_json_object(text)
    suggestions = _normalize_candidates(parsed)
    assistant_message = str(
        parsed.get("message")
        or "Here are two design candidates. Select one to preview."
    ).strip()

    return {
        "message": assistant_message,
        "suggestions": suggestions,
        "dual_side": bool(dual_side),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
        },
    }
