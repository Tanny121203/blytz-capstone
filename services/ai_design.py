"""
Gemini wrapper for Blytz Stage O / O.1 — two Fabric-compatible design candidates.

Apps import this module; do not call the Gemini HTTP API from views directly.
Never log full prompts or canvas JSON.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

CANDIDATES_REQUIRED = 2


def _system_prompt(*, dual_side: bool, image_present: bool = False) -> str:
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

    image_note = ""
    if image_present:
        image_note = """
A reference image is attached to this turn. Use it as design guidance:
- Extract relevant characteristics: colors, typography, patterns, composition,
  decorative elements.
- Do NOT reproduce the entire photograph, the model wearing it, the physical
  garment shape, or the background.
- Adapt the extracted characteristics to the current Blytz garment template
  and print-area constraints.
- Preserve the existing design elements unless the customer explicitly asked
  for a redesign.
"""

    return f"""You are Blytz's apparel design assistant for a Fabric.js editor.

The customer message is a DESIGN INSTRUCTION, not literal canvas text.
Interpret what they want drawn (words, shapes, colors, layout). Never paste the
full user prompt into any text/IText/textbox. If they say 'Add a large red text
that says TEST', the text content must be exactly "TEST".

CREATIVE COMPOSITION & COMPLEXITY:
- Generate detailed, professionally composed vector artwork. Infer suitable supporting elements, decorative framing, and background accents rather than relying solely on sparse or literal primitives.
- When cultural, festival, or thematic motifs are requested (e.g. tribal patterns, festival geometry, ornate crests), construct rich, intricate arrangements using multiple coordinated geometric objects (circles, polygons, paths, rects) with deliberate symmetry, balanced spacing, hierarchy, and a cohesive color palette matching or complementing the garment.
- Ensure artwork fills the primary printable panel. IMPORTANT: Use a maximum of 25 objects per candidate. Do not generate dense pixel-art grids of tiny rectangles. For complex shapes like hearts or logos, use a few large polygons or a single path object instead of hundreds of small shapes.
- If the customer prohibits words (e.g. "no words"), do not include any text or IText objects.

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

{image_note}
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
    provider = (getattr(settings, "AI_DESIGN_PROVIDER", "") or "gemini").strip().lower()
    if provider == "openai":
        key = getattr(settings, "OPENAI_API_KEY", "") or ""
        return bool(str(key).strip())
    if provider == "groq":
        key = getattr(settings, "GROQ_API_KEY", "") or ""
        return bool(str(key).strip())
    if provider == "mistral":
        key = getattr(settings, "MISTRAL_API_KEY", "") or ""
        return bool(str(key).strip())
    if provider == "cerebras":
        key = getattr(settings, "CEREBRAS_API_KEY", "") or ""
        return bool(str(key).strip())
    key = getattr(settings, "GEMINI_API_KEY", "") or ""
    return bool(str(key).strip())


def vision_configured() -> bool:
    """
    True when AI is live AND the active provider supports image input.
    """
    provider = (
        getattr(settings, "AI_DESIGN_PROVIDER", "gemini") or "gemini"
    ).strip().lower()
    
    if provider == "gemini":
        return bool((getattr(settings, "GEMINI_API_KEY", "") or "").strip())
    if provider == "deepseek":
        return bool((getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip())
        
    # OpenAI, Groq, Mistral, Cerebras are currently text-only or gated
    return False


def _groq_structured_output_schema() -> dict[str, Any]:
    """
    Groq Strict Structured Output JSON Schema for Blytz design suggestions.
    Strict requirements:
    - additionalProperties: false on every object.
    - All properties listed in required.
    - Nullable types expressed as ["type", "null"].
    """
    canvas_object_schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "left": {"type": "number"},
            "top": {"type": "number"},
            "width": {"type": ["number", "null"]},
            "height": {"type": ["number", "null"]},
            "fill": {"type": ["string", "null"]},
            "stroke": {"type": ["string", "null"]},
            "strokeWidth": {"type": ["number", "null"]},
            "text": {"type": ["string", "null"]},
            "fontSize": {"type": ["number", "null"]},
            "fontFamily": {"type": ["string", "null"]},
            "fontWeight": {"type": ["string", "null"]},
            "textAlign": {"type": ["string", "null"]},
            "angle": {"type": ["number", "null"]},
            "opacity": {"type": ["number", "null"]},
            "scaleX": {"type": ["number", "null"]},
            "scaleY": {"type": ["number", "null"]},
            "rx": {"type": ["number", "null"]},
            "ry": {"type": ["number", "null"]},
            "src": {"type": ["string", "null"]},
            "blytzId": {"type": ["string", "null"]},
            "id": {"type": ["string", "null"]},
        },
        "required": [
            "type",
            "left",
            "top",
            "width",
            "height",
            "fill",
            "stroke",
            "strokeWidth",
            "text",
            "fontSize",
            "fontFamily",
            "fontWeight",
            "textAlign",
            "angle",
            "opacity",
            "scaleX",
            "scaleY",
            "rx",
            "ry",
            "src",
            "blytzId",
            "id",
        ],
        "additionalProperties": False,
    }

    canvas_payload_schema = {
        "type": "object",
        "properties": {
            "schema_version": {"type": "integer"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "canvas": {
                "type": "object",
                "properties": {
                    "version": {"type": "string"},
                    "objects": {
                        "type": "array",
                        "items": canvas_object_schema,
                    },
                },
                "required": ["version", "objects"],
                "additionalProperties": False,
            },
        },
        "required": ["schema_version", "width", "height", "canvas"],
        "additionalProperties": False,
    }

    candidate_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "label": {"type": "string"},
            "description": {"type": "string"},
            "canvasJSON": canvas_payload_schema,
            "otherSideCanvasJSON": canvas_payload_schema,
        },
        "required": [
            "id",
            "label",
            "description",
            "canvasJSON",
            "otherSideCanvasJSON",
        ],
        "additionalProperties": False,
    }

    root_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "candidates": {
                "type": "array",
                "items": candidate_schema,
            },
        },
        "required": ["message", "candidates"],
        "additionalProperties": False,
    }
    return root_schema


def _call_openai_compatible(
    *,
    endpoint_url: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    api_key: str,
    model: str,
    provider_name: str,
    max_tokens: int = 4096,
    timeout: float = 60,
    scope: str = "redesign",
    original_canvas_json: dict | None = None,
    reference_image: dict | None = None,
) -> dict[str, Any]:
    if provider_name in ("groq", "mistral", "cerebras") and reference_image is not None:
        raise AIDesignError(
            "Image input is not supported by the current provider.",
            code="ai_validation",
        )

    user_content: Any = (
        "Customer request and structured garment/print context "
        "(JSON). Prefer print_areas; slight overflow OK.\n"
        + json.dumps(user_payload, ensure_ascii=False)
    )
    if provider_name in ("openai", "deepseek") and reference_image is not None:
        user_content = [
            {
                "type": "text",
                "text": (
                    "Customer request and structured garment/print context "
                    "(JSON). Prefer print_areas; slight overflow OK.\n"
                    + json.dumps(user_payload, ensure_ascii=False)
                ),
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{reference_image['mime_type']};base64,{reference_image['data']}"
                },
            },
        ]

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    system_prompt
                    + "\n\nCRITICAL FORMAT REQUIREMENT: You must output ONLY valid JSON matching the exact schema specified above. Do not include any conversational preamble, markdown code fences, or trailing text. The response must start with '{' and end with '}'."
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    if provider_name == "groq":
        body["include_reasoning"] = False
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "blytz_design_suggestions",
                "strict": True,
                "schema": _groq_structured_output_schema(),
            },
        }
    else:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if provider_name in ("groq", "cerebras"):
        headers["User-Agent"] = "BlytzClothing/1.0"

    req = urllib.request.Request(
        endpoint_url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    import time
    max_retries = 3
    last_exception = None
    try:
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    status = getattr(resp, "status", 200)
                break  # success, exit loop
            except urllib.error.HTTPError as exc:
                if exc.code == 503 and attempt < max_retries - 1:
                    last_exception = exc
                    time.sleep(2 ** attempt)  # exponential backoff
                    continue
                raise exc
            except (TimeoutError, socket.timeout) as exc:
                if attempt < max_retries - 1:
                    last_exception = exc
                    time.sleep(2 ** attempt)
                    continue
                raise exc
    except urllib.error.HTTPError as exc:
        status_code = getattr(exc, "code", "?")
        reason = ""
        err_code = "ai_upstream"
        err_type = ""
        failed_gen = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:1000]
            err_json = json.loads(err_body)
            err_obj = err_json.get("error") if isinstance(err_json, dict) else None
            if isinstance(err_obj, dict):
                reason = str(
                    err_obj.get("message")
                    or err_obj.get("status")
                    or err_obj.get("code")
                    or ""
                )[:300]
                err_code_raw = str(err_obj.get("code") or "").lower()
                err_type = str(err_obj.get("type") or "").lower()
                failed_gen = str(err_obj.get("failed_generation") or "")[:200]
                if "insufficient_quota" in err_code_raw or "quota" in reason.lower() or "quota" in err_type:
                    err_code = "ai_quota"
                elif "rate_limit" in err_code_raw or status_code == 429:
                    err_code = "ai_rate_limit"
                elif status_code == 403:
                    if (
                        "model" in err_code_raw
                        or "model" in err_type
                        or "not_found" in err_code_raw
                        or "organization" in reason.lower()
                        or "project" in reason.lower()
                        or "disabled" in reason.lower()
                    ):
                        err_code = "ai_model_permission"
                    else:
                        err_code = "ai_forbidden"
                elif status_code == 400:
                    if "json" in reason.lower() or "validate" in reason.lower() or "schema" in reason.lower():
                        err_code = "ai_parse"
            elif err_body:
                reason = err_body[:120].replace("\n", " ")
        except Exception:
            reason = ""
        logger.warning(
            "ai_suggest %s_http_error status=%s model=%s code=%s type=%s reason=%s failed_generation_present=%s",
            provider_name,
            status_code,
            model,
            err_code,
            err_type,
            reason,
            bool(failed_gen),
        )
        if status_code == 401:
            raise AIDesignError(
                f"AI suggestions are unavailable ({provider_name.capitalize()} API key rejected).",
                code="ai_unavailable",
            ) from exc
        if status_code == 403:
            if err_code == "ai_model_permission":
                detail_msg = reason if reason else f"Selected model {model} is not available or permitted on your {provider_name.capitalize()} account."
                raise AIDesignError(
                    f"AI suggestions are unavailable ({detail_msg}).",
                    code="ai_model_permission",
                ) from exc
            detail_msg = reason if reason else f"{provider_name.capitalize()} access forbidden / 403."
            raise AIDesignError(
                f"AI suggestions are unavailable ({detail_msg}).",
                code="ai_forbidden",
            ) from exc
        if status_code == 429:
            if err_code == "ai_quota":
                raise AIDesignError(
                    f"AI suggestions are unavailable ({provider_name.capitalize()} API quota or credits exhausted).",
                    code="ai_quota",
                ) from exc
            raise AIDesignError(
                "AI rate limit exceeded. Please try again later.",
                code="ai_rate_limit",
            ) from exc
        if status_code == 400:
            if err_code == "ai_parse":
                detail_msg = reason if reason else "Model failed to generate valid JSON according to requirements."
                raise AIDesignError(
                    f"AI suggestion request failed: {detail_msg}",
                    code="ai_parse",
                ) from exc
        if status_code in (401, 403):
            raise AIDesignError(
                f"AI suggestions are unavailable ({provider_name.capitalize()} API access rejected).",
                code="ai_unavailable",
            ) from exc
        raise AIDesignError(
            "AI service request failed. Please try again.",
            code=err_code,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        logger.warning("ai_suggest %s_timeout timeout_seconds=%s", provider_name, timeout)
        raise AIDesignError(
            "AI service request timed out. Please try again later.",
            code="ai_timeout",
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)) or "timeout" in str(exc.reason).lower():
            logger.warning("ai_suggest %s_timeout timeout_seconds=%s", provider_name, timeout)
            raise AIDesignError(
                "AI service request timed out. Please try again later.",
                code="ai_timeout",
            ) from exc
        logger.warning("ai_suggest %s_network_error", provider_name)
        raise AIDesignError(
            "AI service is unreachable. Please try again later.",
            code="ai_upstream",
        ) from exc
    except urllib.error.URLError as exc:
        logger.warning("ai_suggest %s_network_error", provider_name)
        raise AIDesignError(
            "AI service is unreachable. Please try again later.",
            code="ai_upstream",
        ) from exc

    if status >= 400:
        logger.warning("ai_suggest %s_bad_status status=%s", provider_name, status)
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

    usage = envelope.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")

    try:
        choices = envelope.get("choices", [])
        if not choices:
            raise AIDesignError("AI service returned no choices.", code="ai_parse")
        first_choice = choices[0]
        finish_reason = str(first_choice.get("finish_reason") or "").lower()
        if finish_reason == "length":
            logger.warning(
                "ai_suggest %s_length_exceeded model=%s prompt_tokens=%s completion_tokens=%s",
                provider_name,
                model,
                prompt_tokens,
                output_tokens,
            )
            raise AIDesignError(
                "AI response was cut off due to token limits. Please try again.",
                code="ai_length",
            )
        msg_obj = first_choice.get("message") or {}
        content = str(msg_obj.get("content") or "")
        if not content.strip():
            raise AIDesignError("AI service returned an empty response.", code="ai_empty")
    except (AttributeError, TypeError) as exc:
        raise AIDesignError(
            "AI service returned an unexpected shape.", code="ai_parse"
        ) from exc

    parsed = _extract_json_object(content)
    if scope in ("color", "text"):
        suggestions = _normalize_patch_candidates(parsed, original_canvas_json=original_canvas_json or {}, scope=scope)
    else:
        suggestions = _normalize_candidates(parsed)
    assistant_message = str(
        parsed.get("message")
        or "Here are two design candidates. Select one to preview."
    ).strip()

    res = {
        "message": assistant_message,
        "suggestions": suggestions,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
        },
    }
    if scope in ("color", "text"):
        res["scope"] = scope
    return res


def _call_openai(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    api_key: str,
    model: str,
    scope: str = "redesign",
    original_canvas_json: dict | None = None,
    reference_image: dict | None = None,
) -> dict[str, Any]:
    return _call_openai_compatible(
        endpoint_url="https://api.openai.com/v1/chat/completions",
        system_prompt=system_prompt,
        user_payload=user_payload,
        api_key=api_key,
        model=model,
        provider_name="openai",
        scope=scope,
        original_canvas_json=original_canvas_json,
        reference_image=reference_image,
    )


def _call_groq(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    api_key: str,
    model: str,
    scope: str = "redesign",
    original_canvas_json: dict | None = None,
    reference_image: dict | None = None,
) -> dict[str, Any]:
    return _call_openai_compatible(
        endpoint_url="https://api.groq.com/openai/v1/chat/completions",
        system_prompt=system_prompt,
        user_payload=user_payload,
        api_key=api_key,
        model=model,
        provider_name="groq",
        scope=scope,
        original_canvas_json=original_canvas_json,
        reference_image=reference_image,
    )


def _call_mistral(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    api_key: str,
    model: str,
    scope: str = "redesign",
    original_canvas_json: dict | None = None,
    reference_image: dict | None = None,
) -> dict[str, Any]:
    return _call_openai_compatible(
        endpoint_url="https://api.mistral.ai/v1/chat/completions",
        system_prompt=system_prompt,
        user_payload=user_payload,
        api_key=api_key,
        model=model,
        provider_name="mistral",
        scope=scope,
        original_canvas_json=original_canvas_json,
        reference_image=reference_image,
    )


def _call_cerebras(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    api_key: str,
    model: str,
    scope: str = "redesign",
    original_canvas_json: dict | None = None,
    reference_image: dict | None = None,
) -> dict[str, Any]:
    max_tokens = getattr(settings, "CEREBRAS_MAX_TOKENS", 4096)
    return _call_openai_compatible(
        endpoint_url="https://api.cerebras.ai/v1/chat/completions",
        system_prompt=system_prompt,
        user_payload=user_payload,
        api_key=api_key,
        model=model,
        provider_name="cerebras",
        max_tokens=max_tokens,
        scope=scope,
        original_canvas_json=original_canvas_json,
        reference_image=reference_image,
    )


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


def _patch_prompt(*, scope: str, dual_side: bool, image_present: bool = False) -> str:
    dual_block = ""
    if dual_side:
        dual_block = """
Dual-side mode is ON for this turn:
- The customer has requested a change that applies to the active side only. Do not modify objects on the other side.
"""

    image_note = ""
    if image_present:
        image_note = """
A reference image is attached to this turn. Use it as design guidance:
- Extract relevant characteristics: colors, typography, patterns, composition,
  decorative elements.
- Do NOT reproduce the entire photograph, the model wearing it, the physical
  garment shape, or the background.
- Adapt the extracted characteristics to the current Blytz garment template
  and print-area constraints.
- Preserve the existing design elements unless the customer explicitly asked
  for a redesign.
"""

    if scope == "text":
        return f"""You are Blytz's text-adjustment assistant. Do not generate new canvas JSON.

Return ONLY a single JSON object with this exact shape:
{{
  "message": "short assistant reply to the customer",
  "candidates": [
    {{
      "id": "candidate-a",
      "label": "short label",
      "description": "one-line description",
      "patches": [
        {{"blytzId": "...", "property": "text", "value": "New Text"}}
      ]
    }},
    {{
      "id": "candidate-b",
      "label": "short label",
      "description": "one-line description",
      "patches": [
        {{"blytzId": "...", "property": "text", "value": "New Text"}}
      ]
    }}
  ]
}}

{dual_block}

{image_note}
Allowed properties for this mode, listed explicitly: text, fontSize, fontFamily, fontWeight, fontStyle, fill, stroke.
- Every blytzId must reference a text, IText, or textbox object in current_canvas. Do not patch rectangles, circles, ellipses, paths, lines, polygons, or images.
- Do not change left, top, width, height, angle, scaleX, scaleY, type, or any property not in the allowed list above.
- Do not add, remove, reorder, resize, or move any object. The text object's bounding box will be recalculated by the editor after load.
- Property value types: text and fontFamily and fontStyle and fontWeight are strings; fontSize is a number (integer); fill and stroke are strings (#rrggbb or a CSS color keyword).
- If the instruction cannot be fulfilled as text-only, return patches: [] for that candidate and explain briefly in message.
- Return exactly two candidates. If two meaningfully different interpretations exist, produce two; otherwise produce the same candidate twice.
"""
    return f"""You are Blytz's color-adjustment assistant. Do not generate new canvas JSON.

Return ONLY a single JSON object with this exact shape:
{{
  "message": "short assistant reply to the customer",
  "candidates": [
    {{
      "id": "candidate-a",
      "label": "short label",
      "description": "one-line description",
      "patches": [
        {{"blytzId": "...", "property": "fill", "value": "#rrggbb"}}
      ]
    }},
    {{
      "id": "candidate-b",
      "label": "short label",
      "description": "one-line description",
      "patches": [
        {{"blytzId": "...", "property": "fill", "value": "#rrggbb"}}
      ]
    }}
  ]
}}

{dual_block}

{image_note}
Hard rules:
- Every blytzId must be copied verbatim from an object in current_canvas.
- Only fill and stroke may be changed. Do not change left, top, width, height, angle, scaleX, scaleY, type, text, fontSize, fontFamily, fontWeight, or any other property.
- Do not add, remove, reorder, resize, move, or rotate any object.
- If the instruction cannot be fulfilled as color-only, return patches: [] for that candidate and explain briefly in message.
- Return exactly two candidates. If two meaningfully different color assignments are possible, produce two; if only one is sensible, produce it twice.
"""


def _normalize_patch_candidates(payload: dict, *, original_canvas_json: dict, scope: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise AIDesignError(
            "AI returned malformed color suggestions. Please retry.",
            code="ai_validation",
        )
    from apps.designs.ai_suggest import TEXT_PATCHABLE_PROPERTIES, TEXT_OBJECT_TYPES

    if scope == "color":
        allowed_props = {"fill", "stroke"}
    elif scope == "text":
        allowed_props = TEXT_PATCHABLE_PROPERTIES
    else:
        raise AIDesignError(code="ai_validation", message="Unsupported scope for patch mode")

    candidates = payload.get("candidates") or payload.get("suggestions")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise AIDesignError(
            "AI returned malformed color suggestions. Please retry.",
            code="ai_validation",
        )
    orig_canvas = original_canvas_json.get("canvas", {}) if isinstance(original_canvas_json, dict) else {}
    orig_objs = orig_canvas.get("objects", []) if isinstance(orig_canvas, dict) else {}
    orig_map = {str(o.get("blytzId")): o for o in orig_objs if o.get("blytzId") is not None}
    valid_ids = set(orig_map.keys())

    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise AIDesignError(
                "AI returned malformed color suggestions. Please retry.",
                code="ai_validation",
            )
        patches_raw = item.get("patches")
        if not isinstance(patches_raw, list):
            patches_raw = []
        normalized_patches = []
        for p in patches_raw:
            if not isinstance(p, dict):
                raise AIDesignError(
                    "AI returned malformed color suggestions. Please retry.",
                    code="ai_validation",
                )
            bid = str(p.get("blytzId") or "")
            prop = str(p.get("property") or "").strip()
            val = p.get("value")
            if bid not in valid_ids or prop not in allowed_props:
                raise AIDesignError(
                    "AI returned malformed color suggestions. Please retry.",
                    code="ai_validation",
                )
            if scope == "text":
                target_obj = orig_map[bid]
                if str(target_obj.get("type", "")) not in TEXT_OBJECT_TYPES:
                    raise AIDesignError(
                        code="ai_validation",
                        message="Text patch targets a non-text object",
                    )
            normalized_patches.append({"blytzId": bid, "property": prop, "value": val})

        cid = str(item.get("id") or f"candidate-{i + 1}")
        entry: dict[str, Any] = {
            "id": cid,
            "label": str(item.get("label") or f"Option {i + 1}")[:80],
            "description": str(item.get("description") or "")[:240],
            "patches": normalized_patches,
        }
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
    scope: str = "redesign",
    reference_image: dict | None = None,
) -> dict[str, Any]:
    """
    Call Gemini or OpenAI and return {message, suggestions, usage, dual_side}.

    Raises AIDesignError on configuration / transport / parse failures.
    Does not validate canvas schema (caller must).
    """
    provider = (getattr(settings, "AI_DESIGN_PROVIDER", "") or "gemini").strip().lower()
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

    if scope not in ("redesign", "color", "text"):
        raise AIDesignError("Unsupported scope", code="ai_validation")

    image_present = reference_image is not None
    if scope == "redesign":
        system_prompt = _system_prompt(dual_side=dual_side, image_present=image_present)
    else:
        system_prompt = _patch_prompt(scope=scope, dual_side=dual_side, image_present=image_present)

    if provider == "openai":
        api_key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
        if not api_key:
            raise AIDesignError(
                "AI suggestions are unavailable (no OpenAI API key configured).",
                code="ai_unavailable",
            )
        model = (
            getattr(settings, "OPENAI_MODEL", "") or "gpt-4o-mini"
        ).strip() or "gpt-4o-mini"
        res = _call_openai(
            system_prompt=system_prompt,
            user_payload=user_payload,
            api_key=api_key,
            model=model,
            scope=scope,
            original_canvas_json=canvas_json,
            reference_image=reference_image,
        )
        res["dual_side"] = bool(dual_side)
        return res

    if provider == "groq":
        api_key = (getattr(settings, "GROQ_API_KEY", "") or "").strip()
        if not api_key:
            raise AIDesignError(
                "AI suggestions are unavailable (no Groq API key configured).",
                code="ai_unavailable",
            )
        model = (
            getattr(settings, "GROQ_MODEL", "") or "llama-3.3-70b-versatile"
        ).strip() or "llama-3.3-70b-versatile"
        res = _call_groq(
            system_prompt=system_prompt,
            user_payload=user_payload,
            api_key=api_key,
            model=model,
            scope=scope,
            original_canvas_json=canvas_json,
            reference_image=reference_image,
        )
        res["dual_side"] = bool(dual_side)
        return res

    if provider == "mistral":
        api_key = (getattr(settings, "MISTRAL_API_KEY", "") or "").strip()
        if not api_key:
            raise AIDesignError(
                "AI suggestions are unavailable (no Mistral API key configured).",
                code="ai_unavailable",
            )
        model = (
            getattr(settings, "MISTRAL_MODEL", "") or "mistral-small-latest"
        ).strip() or "mistral-small-latest"
        res = _call_mistral(
            system_prompt=system_prompt,
            user_payload=user_payload,
            api_key=api_key,
            model=model,
            scope=scope,
            original_canvas_json=canvas_json,
            reference_image=reference_image,
        )
        res["dual_side"] = bool(dual_side)
        return res

    if provider == "cerebras":
        api_key = (getattr(settings, "CEREBRAS_API_KEY", "") or "").strip()
        if not api_key:
            raise AIDesignError(
                "AI suggestions are unavailable (no Cerebras API key configured).",
                code="ai_unavailable",
            )
        model = (
            getattr(settings, "CEREBRAS_MODEL", "") or "llama3.1-70b"
        ).strip() or "llama3.1-70b"
        res = _call_cerebras(
            system_prompt=system_prompt,
            user_payload=user_payload,
            api_key=api_key,
            model=model,
            scope=scope,
            original_canvas_json=canvas_json,
            reference_image=reference_image,
        )
        res["dual_side"] = bool(dual_side)
        return res
    if provider == "deepseek":
        api_key = (getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip()
        if not api_key:
            raise AIDesignError(
                "AI suggestions are unavailable (no DeepSeek API key configured).",
                code="ai_unavailable",
            )
        model = (getattr(settings, "DEEPSEEK_MODEL", "") or "deepseek-flash").strip()
        base_url = (getattr(settings, "DEEPSEEK_BASE_URL", "") or "https://api.deepseek.com/v1").strip()
        res = _call_openai_compatible(
            system_prompt=system_prompt,
            user_payload=user_payload,
            api_key=api_key,
            model=model,
            endpoint_url=f"{base_url.rstrip('/')}/chat/completions",
            provider_name="deepseek",
            max_tokens=32768,
            scope=scope,
            original_canvas_json=canvas_json,
            reference_image=reference_image,
        )
        res["dual_side"] = bool(dual_side)
        return res

    # Default: Gemini
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise AIDesignError(
            "AI suggestions are unavailable (no API key configured).",
            code="ai_unavailable",
        )

    if scope == "redesign":
        model = (getattr(settings, "GEMINI_REDESIGN_MODEL", "") or "gemini-3.6-flash").strip() or "gemini-3.6-flash"
    else:
        model = (getattr(settings, "GEMINI_MODEL", "") or "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"

    user_parts: list[dict[str, Any]] = [
        {
            "text": (
                "Customer request and structured garment/print context "
                "(JSON). Prefer print_areas; slight overflow OK.\n"
                + json.dumps(user_payload, ensure_ascii=False)
            )
        }
    ]
    if reference_image is not None:
        user_parts.append({
            "inlineData": {
                "mimeType": reference_image["mime_type"],
                "data": reference_image["data"],
            }
        })

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": user_parts,
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    timeout = getattr(settings, "GEMINI_REQUEST_TIMEOUT", 120)
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
    import time
    max_retries = 3
    last_exception = None
    try:
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    status = getattr(resp, "status", 200)
                break  # success, exit loop
            except urllib.error.HTTPError as exc:
                if exc.code == 503 and attempt < max_retries - 1:
                    last_exception = exc
                    time.sleep(2 ** attempt)
                    continue
                raise exc
            except (TimeoutError, socket.timeout) as exc:
                if attempt < max_retries - 1:
                    last_exception = exc
                    time.sleep(2 ** attempt)
                    continue
                raise exc
    except (TimeoutError, socket.timeout) as exc:
        logger.warning("ai_suggest gemini_timeout timeout_seconds=%s", timeout)
        raise AIDesignError(
            "AI service request timed out. Please try again later.",
            code="ai_timeout",
        ) from exc
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
        if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)) or "timeout" in str(exc.reason).lower():
            logger.warning("ai_suggest gemini_timeout timeout_seconds=%s", timeout)
            raise AIDesignError(
                "AI service request timed out. Please try again later.",
                code="ai_timeout",
            ) from exc
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
    if scope in ("color", "text"):
        suggestions = _normalize_patch_candidates(parsed, original_canvas_json=canvas_json or {}, scope=scope)
    else:
        suggestions = _normalize_candidates(parsed)
    assistant_message = str(
        parsed.get("message")
        or "Here are two design candidates. Select one to preview."
    ).strip()

    res = {
        "message": assistant_message,
        "suggestions": suggestions,
        "dual_side": bool(dual_side),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
        },
    }
    if scope in ("color", "text"):
        res["scope"] = scope
    return res
