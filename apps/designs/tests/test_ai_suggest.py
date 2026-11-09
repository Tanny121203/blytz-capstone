"""Stage O — AI suggest endpoint (Gemini mocked)."""

from __future__ import annotations

import json
import base64
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.designs.models import Design
from services.ai_design import AIDesignError, vision_configured, suggest_design_candidates
from apps.designs.ai_suggest import validate_reference_image, detect_scope, AISuggestValidationError

User = get_user_model()

# Objects placed inside tee/hoodie primary front panel (Stage O.1.2 full flat).
VALID_CANDIDATE_A = {
    "schema_version": 1,
    "width": 800,
    "height": 800,
    "canvas": {
        "version": "6.6.1",
        "objects": [
            {
                "type": "IText",
                "left": 300,
                "top": 280,
                "text": "ALPHA",
                "fontSize": 36,
                "fill": "#0a0a0a",
                "width": 120,
                "height": 40,
            }
        ],
    },
}

VALID_CANDIDATE_B = {
    "schema_version": 1,
    "width": 800,
    "height": 800,
    "canvas": {
        "version": "6.6.1",
        "objects": [
            {
                "type": "Rect",
                "left": 320,
                "top": 300,
                "width": 80,
                "height": 80,
                "fill": "#c9a227",
            }
        ],
    },
}

OUT_OF_BOUNDS_CANDIDATE = {
    "schema_version": 1,
    "width": 800,
    "height": 800,
    "canvas": {
        "version": "6.6.1",
        "objects": [
            {
                "type": "IText",
                "left": 10,
                "top": 10,
                "text": "OUT",
                "fontSize": 36,
                "fill": "#0a0a0a",
                "width": 80,
                "height": 40,
            }
        ],
    },
}


def _ok_gemini_result():
    return {
        "message": "Two options for you.",
        "suggestions": [
            {
                "id": "a",
                "label": "Wordmark",
                "description": "Bold text",
                "canvasJSON": VALID_CANDIDATE_A,
            },
            {
                "id": "b",
                "label": "Badge",
                "description": "Gold square",
                "canvasJSON": VALID_CANDIDATE_B,
            },
        ],
        "usage": {"prompt_tokens": 12, "output_tokens": 34},
    }


@override_settings(
    GEMINI_API_KEY="test-gemini-key-not-real",
    AI_SUGGEST_RATE_LIMIT_PER_HOUR=5,
    AI_SUGGEST_RATE_LIMIT_WINDOW_SECONDS=3600,
)
class DesignAISuggestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.customer = User.objects.create_user(
            email="ai-customer@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="ai-other@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.staff = User.objects.create_user(
            email="ai-staff@example.com",
            password="test-pass-123",
            role=User.Role.STAFF,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="AI test design",
            garment_template="tee",
            garment_color="white",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {"version": "6.6.1", "objects": []},
            },
        )
        self.url = reverse("design_ai_suggest", args=[self.design.pk])
        self.original_canvas = json.loads(json.dumps(self.design.canvas_json))

    def _post(self, user=None, payload=None):
        if user is None:
            user = self.customer
        self.client.force_login(user)
        body = payload if payload is not None else {
            "message": "Bold wordmark",
            "canvas_json": {
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {"version": "6.6.1", "objects": []},
            },
            "active_side": "front",
        }
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_staff_forbidden(self):
        response = self._post(user=self.staff)
        self.assertEqual(response.status_code, 403)

    def test_other_customer_gets_404(self):
        response = self._post(user=self.other)
        self.assertEqual(response.status_code, 404)

    @patch("apps.designs.views.suggest_design_candidates", return_value=_ok_gemini_result())
    def test_success_returns_exactly_two_candidates(self, _mock):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        self.assertEqual(data["suggestions"][0]["canvasJSON"]["schema_version"], 1)
        self.assertNotIn("views", data["suggestions"][0]["canvasJSON"])
        self.assertNotIn("views", data["suggestions"][1]["canvasJSON"])
        # Must not mutate stored design.
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json, self.original_canvas)

    def test_rejects_empty_message(self):
        response = self._post(payload={"message": "  ", "active_side": "front"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_rejects_bad_active_side(self):
        response = self._post(
            payload={"message": "hi", "active_side": "sideways", "canvas_json": {}}
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.designs.views.suggest_design_candidates")
    def test_rejects_malformed_candidates_whole_turn(self, mock_suggest):
        bad = dict(_ok_gemini_result())
        bad["suggestions"] = [
            {
                "id": "a",
                "label": "Bad",
                "canvasJSON": {"schema_version": 1, "canvas": {"objects": "nope"}},
            },
            {
                "id": "b",
                "label": "Ok",
                "canvasJSON": VALID_CANDIDATE_B,
            },
        ]
        mock_suggest.return_value = bad
        response = self._post()
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["code"], "invalid_candidates")

    @patch("apps.designs.views.suggest_design_candidates")
    def test_rejects_views_key_on_candidate(self, mock_suggest):
        with_views = dict(_ok_gemini_result())
        cand = json.loads(json.dumps(VALID_CANDIDATE_A))
        cand["views"] = {"back": {"objects": []}}
        with_views["suggestions"][0]["canvasJSON"] = cand
        mock_suggest.return_value = with_views
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_candidates")

    @patch(
        "apps.designs.views.suggest_design_candidates",
        side_effect=AIDesignError("down", code="ai_unavailable"),
    )
    def test_ai_unavailable_returns_503(self, _mock):
        response = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "ai_unavailable")

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="")
    def test_missing_key_returns_503_without_calling_gemini(self):
        with patch("apps.designs.views.suggest_design_candidates") as mock_suggest:
            response = self._post()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["code"], "ai_unavailable")
            mock_suggest.assert_not_called()

    @patch("apps.designs.views.suggest_design_candidates", return_value=_ok_gemini_result())
    def test_rate_limit_five_successful_per_hour(self, mock_suggest):
        for i in range(5):
            response = self._post()
            self.assertEqual(response.status_code, 200, f"call {i + 1}")
        sixth = self._post()
        self.assertEqual(sixth.status_code, 429)
        self.assertEqual(sixth.json()["code"], "rate_limited")
        self.assertEqual(mock_suggest.call_count, 5)

    @patch("apps.designs.views.suggest_design_candidates")
    def test_failed_calls_do_not_consume_rate_limit(self, mock_suggest):
        mock_suggest.side_effect = AIDesignError("parse", code="ai_parse")
        for _ in range(3):
            response = self._post()
            self.assertEqual(response.status_code, 400)
        mock_suggest.side_effect = None
        mock_suggest.return_value = _ok_gemini_result()
        for i in range(5):
            response = self._post()
            self.assertEqual(response.status_code, 200, f"success {i + 1}")

    @patch("apps.designs.views.suggest_design_candidates", return_value=_ok_gemini_result())
    def test_passes_active_side_and_canvas_context(self, mock_suggest):
        ctx = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [{"type": "IText", "text": "CTX", "left": 1, "top": 1}],
            },
        }
        response = self._post(
            payload={
                "message": "Refine this",
                "canvas_json": ctx,
                "active_side": "back",
            }
        )
        self.assertEqual(response.status_code, 200)
        kwargs = mock_suggest.call_args.kwargs
        self.assertEqual(kwargs["active_side"], "back")
        self.assertEqual(kwargs["message"], "Refine this")
        self.assertEqual(kwargs["canvas_json"]["canvas"]["objects"][0]["text"], "CTX")
        self.assertEqual(kwargs["garment_template"], "tee")
        self.assertTrue(kwargs["print_areas"])
        self.assertEqual(kwargs["print_areas"][0]["id"], "back")
        self.assertFalse(kwargs["dual_side"])

    @patch("apps.designs.views.suggest_design_candidates")
    def test_out_of_bounds_retries_then_ok(self, mock_suggest):
        bad = dict(_ok_gemini_result())
        bad["suggestions"] = [
            {"id": "a", "label": "Bad", "canvasJSON": OUT_OF_BOUNDS_CANDIDATE},
            {"id": "b", "label": "Bad2", "canvasJSON": OUT_OF_BOUNDS_CANDIDATE},
        ]
        mock_suggest.side_effect = [bad, _ok_gemini_result()]
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_suggest.call_count, 2)
        self.assertIsNotNone(mock_suggest.call_args_list[1].kwargs.get("repair_hint"))

    @patch("apps.designs.views.suggest_design_candidates")
    def test_image_preserved_when_ai_omits(self, mock_suggest):
        prior_img = {
            "type": "image",
            "left": 300,
            "top": 300,
            "width": 40,
            "height": 40,
            "src": "data:image/png;base64,aaa",
            "blytzId": "img-keep-1",
        }
        result = _ok_gemini_result()
        mock_suggest.return_value = result
        response = self._post(
            payload={
                "message": "Add a gold badge",
                "active_side": "front",
                "canvas_json": {
                    "schema_version": 1,
                    "width": 800,
                    "height": 800,
                    "canvas": {"version": "6.6.1", "objects": [prior_img]},
                },
            }
        )
        self.assertEqual(response.status_code, 200)
        objs = response.json()["suggestions"][0]["canvasJSON"]["canvas"]["objects"]
        self.assertTrue(any(o.get("blytzId") == "img-keep-1" for o in objs))

    @patch("apps.designs.views.suggest_design_candidates")
    def test_jersey_requests_dual_side(self, mock_suggest):
        self.design.garment_template = "jersey"
        self.design.save(update_fields=["garment_template"])
        dual = _ok_gemini_result()
        for sug in dual["suggestions"]:
            sug["otherSideCanvasJSON"] = json.loads(json.dumps(VALID_CANDIDATE_B))
            # Back panel for jersey: x=275,y=200 — move rect inside
            sug["otherSideCanvasJSON"]["canvas"]["objects"][0].update(
                {"left": 320, "top": 320}
            )
        mock_suggest.return_value = dual
        response = self._post(payload={"message": "Team kit", "active_side": "front"})
        self.assertEqual(response.status_code, 200)
        kwargs = mock_suggest.call_args.kwargs
        self.assertTrue(kwargs["dual_side"])
        self.assertTrue(response.json()["dual_side"])
        self.assertIn("otherSideCanvasJSON", response.json()["suggestions"][0])


class AISuggestValidationUnitTests(TestCase):
    def test_validate_rejects_partial_set(self):
        from apps.designs.ai_suggest import (
            AISuggestValidationError,
            validate_two_candidates,
        )

        with self.assertRaises(AISuggestValidationError):
            validate_two_candidates(
                [{"id": "only", "label": "One", "canvasJSON": VALID_CANDIDATE_A}]
            )

    def test_validate_rejects_far_out_of_bounds(self):
        from apps.designs.ai_suggest import (
            AISuggestValidationError,
            validate_two_candidates,
        )

        with self.assertRaises(AISuggestValidationError):
            validate_two_candidates(
                [
                    {"id": "a", "label": "A", "canvasJSON": OUT_OF_BOUNDS_CANDIDATE},
                    {"id": "b", "label": "B", "canvasJSON": VALID_CANDIDATE_B},
                ],
                garment_template="tee",
                active_side="front",
            )

    def test_validate_allows_small_overflow_within_margin(self):
        """Tee front is x=100,y=160; ±40 soft margin allows ~70,130 (outside strict)."""
        from apps.designs.ai_suggest import validate_two_candidates

        soft = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [
                    {
                        "type": "Rect",
                        "left": 70,
                        "top": 130,
                        "width": 60,
                        "height": 60,
                        "fill": "#c9a227",
                    }
                ],
            },
        }
        out = validate_two_candidates(
            [
                {"id": "a", "label": "A", "canvasJSON": soft},
                {"id": "b", "label": "B", "canvasJSON": VALID_CANDIDATE_B},
            ],
            garment_template="tee",
            active_side="front",
        )
        self.assertEqual(len(out), 2)

    def test_expand_print_areas_clamped(self):
        from apps.designs.ai_suggest import expand_print_areas_for_ai

        areas = [{"id": "front", "name": "Front", "x": 10, "y": 10, "w": 100, "h": 100}]
        soft = expand_print_areas_for_ai(areas, margin_px=40)
        self.assertEqual(soft[0]["x"], 0)
        self.assertEqual(soft[0]["y"], 0)
        self.assertEqual(soft[0]["w"], 150)
        self.assertEqual(soft[0]["h"], 150)

    def test_dual_side_detection(self):
        from apps.designs.ai_suggest import should_generate_dual_side

        self.assertTrue(should_generate_dual_side("jersey", "logo only"))
        self.assertTrue(should_generate_dual_side("tee", "front and back matching set"))
        self.assertFalse(should_generate_dual_side("tee", "chest logo"))


@override_settings(
    AI_DESIGN_PROVIDER="gemini",
    GEMINI_API_KEY="test-gemini-key-not-real",
    GEMINI_MODEL="gemini-3.5-flash-lite",
)
class AISuggestGeminiClientUnitTests(TestCase):
    """Mock urllib — no live Gemini calls."""

    def test_request_url_uses_settings_model(self):
        from services.ai_design import suggest_design_candidates

        gemini_payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "message": "ok",
                                        "candidates": [
                                            {
                                                "id": "a",
                                                "label": "A",
                                                "description": "",
                                                "canvasJSON": VALID_CANDIDATE_A,
                                            },
                                            {
                                                "id": "b",
                                                "label": "B",
                                                "description": "",
                                                "canvasJSON": VALID_CANDIDATE_B,
                                            },
                                        ],
                                    }
                                )
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {},
        }
        raw = json.dumps(gemini_payload).encode("utf-8")

        class _Resp:
            status = 200

            def read(self):
                return raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp()) as mock_open:
            result = suggest_design_candidates(
                message="Add red text TEST",
                canvas_json={},
                active_side="front",
                scope="text",
            )

        self.assertEqual(len(result["suggestions"]), 2)
        req = mock_open.call_args[0][0]
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", req.full_url)
        self.assertNotIn("gemini-2.5-flash", req.full_url)
        self.assertNotIn("gemini-2.0-flash", req.full_url)

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp()) as mock_open:
            result = suggest_design_candidates(
                message="Redesign shirt",
                canvas_json={},
                active_side="front",
                scope="redesign",
            )

        self.assertEqual(len(result["suggestions"]), 2)
        req = mock_open.call_args[0][0]
        self.assertIn("/models/gemini-3.6-flash:generateContent", req.full_url)


@override_settings(
    AI_DESIGN_PROVIDER="mistral",
    MISTRAL_API_KEY="test-mistral-key-not-real",
    MISTRAL_MODEL="mistral-small-latest",
)
class AISuggestMistralClientUnitTests(TestCase):
    """Mock urllib — no live Mistral calls."""

    def test_mistral_request_success_and_model(self):
        from services.ai_design import suggest_design_candidates

        mistral_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "message": "Mistral options ready.",
                                "candidates": [
                                    {
                                        "id": "a",
                                        "label": "Option A",
                                        "description": "Desc A",
                                        "canvasJSON": VALID_CANDIDATE_A,
                                    },
                                    {
                                        "id": "b",
                                        "label": "Option B",
                                        "description": "Desc B",
                                        "canvasJSON": VALID_CANDIDATE_B,
                                    },
                                ],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 25},
        }
        raw = json.dumps(mistral_payload).encode("utf-8")

        class _Resp:
            status = 200

            def read(self):
                return raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp()) as mock_open:
            result = suggest_design_candidates(
                message="Minimalist monogram",
                canvas_json={},
                active_side="front",
            )

        self.assertEqual(len(result["suggestions"]), 2)
        self.assertEqual(result["message"], "Mistral options ready.")
        req = mock_open.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.mistral.ai/v1/chat/completions")
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["model"], "mistral-small-latest")
        self.assertEqual(body_sent["response_format"]["type"], "json_object")
        self.assertNotIn("include_reasoning", body_sent)

    @override_settings(AI_DESIGN_PROVIDER="mistral", MISTRAL_API_KEY="")
    def test_mistral_missing_key_returns_unavailable(self):
        from services.ai_design import suggest_design_candidates, AIDesignError

        with self.assertRaises(AIDesignError) as ctx:
            suggest_design_candidates(
                message="Test",
                canvas_json={},
                active_side="front",
            )
        self.assertEqual(ctx.exception.code, "ai_unavailable")


@override_settings(
    AI_DESIGN_PROVIDER="cerebras",
    CEREBRAS_API_KEY="test-cerebras-key-not-real",
    CEREBRAS_MODEL="llama3.1-8b",
)
class AISuggestCerebrasClientUnitTests(TestCase):
    """Mock urllib — no live Cerebras calls."""

    def test_cerebras_request_success_and_model(self):
        from services.ai_design import suggest_design_candidates

        cerebras_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "message": "Cerebras options ready.",
                                "candidates": [
                                    {
                                        "id": "a",
                                        "label": "Option A",
                                        "description": "Desc A",
                                        "canvasJSON": VALID_CANDIDATE_A,
                                    },
                                    {
                                        "id": "b",
                                        "label": "Option B",
                                        "description": "Desc B",
                                        "canvasJSON": VALID_CANDIDATE_B,
                                    },
                                ],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
        raw = json.dumps(cerebras_payload).encode("utf-8")

        class _Resp:
            status = 200

            def read(self):
                return raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp()) as mock_open:
            result = suggest_design_candidates(
                message="Fast vector design",
                canvas_json={},
                active_side="front",
            )

        self.assertEqual(len(result["suggestions"]), 2)
        self.assertEqual(result["message"], "Cerebras options ready.")
        req = mock_open.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.cerebras.ai/v1/chat/completions")
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["model"], "llama3.1-8b")
        self.assertEqual(body_sent["response_format"]["type"], "json_object")

    @override_settings(AI_DESIGN_PROVIDER="cerebras", CEREBRAS_API_KEY="")
    def test_cerebras_missing_key_returns_unavailable(self):
        from services.ai_design import suggest_design_candidates, AIDesignError

        with self.assertRaises(AIDesignError) as ctx:
            suggest_design_candidates(
                message="Test",
                canvas_json={},
                active_side="front",
            )
        self.assertEqual(ctx.exception.code, "ai_unavailable")

    @override_settings(
        AI_DESIGN_PROVIDER="cerebras",
        CEREBRAS_API_KEY="test-cerebras-key-not-real",
        CEREBRAS_MODEL="qwen-3.8-27b",
        CEREBRAS_MAX_TOKENS=2048,
    )
    def test_cerebras_max_tokens_and_length_truncation_logging(self):
        from services.ai_design import suggest_design_candidates, AIDesignError

        cerebras_payload = {
            "choices": [
                {
                    "message": {"content": ""},
                    "finish_reason": "length",
                }
            ],
            "usage": {"prompt_tokens": 150, "completion_tokens": 2048},
        }
        raw = json.dumps(cerebras_payload).encode("utf-8")

        class _Resp:
            status = 200

            def read(self):
                return raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp()) as mock_open, \
             patch("services.ai_design.logger.warning") as mock_log:
            with self.assertRaises(AIDesignError) as ctx:
                suggest_design_candidates(
                    message="Dense vector design",
                    canvas_json={},
                    active_side="front",
                )
            self.assertEqual(ctx.exception.code, "ai_length")
            
        req = mock_open.call_args[0][0]
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["max_tokens"], 2048)
        self.assertEqual(body_sent["model"], "qwen-3.8-27b")
        mock_log.assert_called_once()
        log_args = mock_log.call_args[0]
        formatted = log_args[0] % log_args[1:]
        self.assertIn("cerebras_length_exceeded", formatted)
        self.assertEqual(log_args[1], "cerebras")     # provider_name
        self.assertEqual(log_args[1], "cerebras")
        self.assertEqual(log_args[2], "qwen-3.8-27b")
        self.assertEqual(log_args[3], 150)
        self.assertEqual(log_args[4], 2048)  # or whatever output_tokens value the test uses
        # self.assertEqual(log_args[3], 2048)
@override_settings(
    AI_DESIGN_PROVIDER="groq",
    GROQ_API_KEY="test-groq-key-not-real",
    GROQ_MODEL="llama-3.3-70b-versatile",
)
class AISuggestGroqClientUnitTests(TestCase):
    """Mock urllib — no live Groq calls."""

    def test_groq_request_success_and_model(self):
        from services.ai_design import suggest_design_candidates

        groq_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "message": "Groq options ready.",
                                "candidates": [
                                    {
                                        "id": "a",
                                        "label": "Option A",
                                        "description": "Desc A",
                                        "canvasJSON": VALID_CANDIDATE_A,
                                    },
                                    {
                                        "id": "b",
                                        "label": "Option B",
                                        "description": "Desc B",
                                        "canvasJSON": VALID_CANDIDATE_B,
                                    },
                                ],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 30},
        }
        raw = json.dumps(groq_payload).encode("utf-8")

        class _Resp:
            status = 200

            def read(self):
                return raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp()) as mock_open:
            result = suggest_design_candidates(
                message="Tribal festival design on hoodie",
                canvas_json={},
                active_side="front",
            )

        self.assertEqual(len(result["suggestions"]), 2)
        self.assertEqual(result["message"], "Groq options ready.")
        req = mock_open.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(req.get_header("User-agent"), "BlytzClothing/1.0")
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["model"], "llama-3.3-70b-versatile")
        self.assertEqual(body_sent["response_format"]["type"], "json_schema")
        self.assertEqual(body_sent["response_format"]["json_schema"]["strict"], True)
        self.assertEqual(body_sent["include_reasoning"], False)
        self.assertNotIn("reasoning_format", body_sent)

    @override_settings(AI_DESIGN_PROVIDER="groq", GROQ_API_KEY="")
    def test_groq_missing_key_returns_unavailable(self):
        from services.ai_design import suggest_design_candidates, AIDesignError

        with self.assertRaises(AIDesignError) as ctx:
            suggest_design_candidates(
                message="Test",
                canvas_json={},
                active_side="front",
            )
        self.assertEqual(ctx.exception.code, "ai_unavailable")

    def test_http_401_authentication_failure(self):
        from services.ai_design import suggest_design_candidates, AIDesignError
        import urllib.error
        import io

        err_payload = json.dumps({
            "error": {"message": "Invalid API Key", "type": "auth_error", "code": "invalid_api_key"}
        }).encode("utf-8")

        http_exc = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(err_payload),
        )

        with patch("services.ai_design.urllib.request.urlopen", side_effect=http_exc):
            with self.assertRaises(AIDesignError) as ctx:
                suggest_design_candidates(message="Test 401", canvas_json={}, active_side="front")
            self.assertEqual(ctx.exception.code, "ai_unavailable")

    def test_http_403_model_permission_restriction(self):
        from services.ai_design import suggest_design_candidates, AIDesignError
        import urllib.error
        import io

        err_payload = json.dumps({
            "error": {"message": "Model not found or access denied", "type": "invalid_request_error", "code": "model_not_found"}
        }).encode("utf-8")

        http_exc = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(err_payload),
        )

        with patch("services.ai_design.urllib.request.urlopen", side_effect=http_exc):
            with self.assertRaises(AIDesignError) as ctx:
                suggest_design_candidates(message="Test 403 model", canvas_json={}, active_side="front")
            self.assertEqual(ctx.exception.code, "ai_model_permission")

    def test_http_403_general_forbidden(self):
        from services.ai_design import suggest_design_candidates, AIDesignError
        import urllib.error
        import io

        err_payload = json.dumps({
            "error": {"message": "Forbidden access", "type": "permission_error", "code": "forbidden"}
        }).encode("utf-8")

        http_exc = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(err_payload),
        )

        with patch("services.ai_design.urllib.request.urlopen", side_effect=http_exc):
            with self.assertRaises(AIDesignError) as ctx:
                suggest_design_candidates(message="Test 403 general", canvas_json={}, active_side="front")
            self.assertEqual(ctx.exception.code, "ai_forbidden")

    def test_http_403_org_level_restriction(self):
        from services.ai_design import suggest_design_candidates, AIDesignError
        import urllib.error
        import io

        err_payload = json.dumps({
            "error": {
                "message": "This model has been disabled for your organization.",
                "type": "invalid_request_error",
                "code": "organization_restricted"
            }
        }).encode("utf-8")

        http_exc = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(err_payload),
        )

        with patch("services.ai_design.urllib.request.urlopen", side_effect=http_exc):
            with self.assertRaises(AIDesignError) as ctx:
                suggest_design_candidates(message="Test 403 org", canvas_json={}, active_side="front")
            self.assertEqual(ctx.exception.code, "ai_model_permission")
            self.assertIn("disabled for your organization", ctx.exception.message)

    def test_http_403_project_level_restriction(self):
        from services.ai_design import suggest_design_candidates, AIDesignError
        import urllib.error
        import io

        err_payload = json.dumps({
            "error": {
                "message": "Model access is not enabled for this project.",
                "type": "invalid_request_error",
                "code": "project_restricted"
            }
        }).encode("utf-8")

        http_exc = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(err_payload),
        )

        with patch("services.ai_design.urllib.request.urlopen", side_effect=http_exc):
            with self.assertRaises(AIDesignError) as ctx:
                suggest_design_candidates(message="Test 403 project", canvas_json={}, active_side="front")
            self.assertEqual(ctx.exception.code, "ai_model_permission")
            self.assertIn("not enabled for this project", ctx.exception.message)


@override_settings(GEMINI_API_KEY="test-key")
class AISuggestScopeStage1Tests(TestCase):
    def setUp(self):
        cache.clear()
        from django.contrib.auth import get_user_model
        from apps.designs.models import Design
        User = get_user_model()
        self.user = User.objects.create_user(
            email="scope-test@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.client.force_login(self.user)
        self.design = Design.objects.create(
            owner=self.user,
            title="Test Design",
            garment_template="tee",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {
                    "version": "6.6.1",
                    "objects": [
                        {"type": "Rect", "blytzId": "obj-1", "left": 250, "top": 250, "width": 100, "height": 100, "fill": "#000"},
                        {"type": "IText", "blytzId": "obj-2", "left": 250, "top": 360, "width": 200, "height": 36, "text": "Hello", "fill": "#111"},
                        {"type": "Circle", "blytzId": "obj-3", "left": 250, "top": 410, "width": 50, "height": 50, "fill": "#222"},
                    ]
                }
            }
        )
        self.url = reverse("design_ai_suggest", args=[self.design.pk])

    def test_detect_scope_color_prompt_returns_color(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("change the colors to red, white, black, and yellow"), "color")

    def test_detect_scope_redesign_prompt_returns_redesign(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("completely redesign this hoodie"), "redesign")

    def test_detect_scope_ambiguous_returns_redesign(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("make it nicer"), "redesign")

    def test_detect_scope_color_plus_add_returns_redesign(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("change colors and add a star"), "redesign")

    def test_detect_scope_hex_returns_color(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("use #ff0000 for everything"), "color")

    def test_apply_patches_changes_only_specified(self):
        from apps.designs.ai_suggest import apply_patches
        canvas = self.design.canvas_json
        patches = [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}]
        patched = apply_patches(canvas, patches)
        
        self.assertEqual(patched["canvas"]["objects"][0]["fill"], "#ff0000")
        import copy
        orig_copy = copy.deepcopy(canvas)
        patched_copy = copy.deepcopy(patched)
        for o_orig, o_patch in zip(orig_copy["canvas"]["objects"], patched_copy["canvas"]["objects"]):
            o_patch.pop("fill", None)
            o_orig.pop("fill", None)
            self.assertEqual(o_orig, o_patch)

    def test_apply_patches_raises_on_unknown_id(self):
        from apps.designs.ai_suggest import apply_patches
        canvas = self.design.canvas_json
        patches = [{"blytzId": "missing", "property": "fill", "value": "#ff0000"}]
        with self.assertRaises(ValueError):
            apply_patches(canvas, patches)

    def test_validate_preservation_passes_clean_patch(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}]
        patched = apply_patches(canvas, patches)
        res = validate_preservation("color", canvas, patched, patches)
        self.assertIsNone(res)

    def test_validate_preservation_rejects_added_object(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}]
        patched = apply_patches(canvas, patches)
        patched["canvas"]["objects"].append({"type": "Rect", "blytzId": "obj-4"})
        with self.assertRaises(ValueError):
            validate_preservation("color", canvas, patched, patches)

    def test_validate_preservation_rejects_removed_object(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}]
        patched = apply_patches(canvas, patches)
        patched["canvas"]["objects"].pop()
        with self.assertRaises(ValueError):
            validate_preservation("color", canvas, patched, patches)

    def test_validate_preservation_rejects_non_whitelisted_property(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "obj-1", "property": "left", "value": 999}]
        patched = apply_patches(canvas, patches)
        with self.assertRaises(ValueError):
            validate_preservation("color", canvas, patched, patches)

    @patch("apps.designs.views.suggest_design_candidates")
    def test_scope_redesign_default_passthrough(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "redesign",
            "message": "Here are two redesign candidates.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Option 1",
                    "description": "Desc 1",
                    "canvasJSON": self.design.canvas_json,
                },
                {
                    "id": "candidate-b",
                    "label": "Option 2",
                    "description": "Desc 2",
                    "canvasJSON": self.design.canvas_json,
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "completely redesign this hoodie", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)

    @patch("apps.designs.views.suggest_design_candidates")
    def test_scope_color_finalizes_to_full_canvas(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "color",
            "message": "Here are two color options.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Red Option",
                    "description": "Red fill",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Blue Option",
                    "description": "Blue fill",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#0000ff"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change colors to red and blue", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        sug0 = data["suggestions"][0]["canvasJSON"]
        self.assertEqual(len(sug0["canvas"]["objects"]), 3)
        self.assertEqual(sug0["canvas"]["objects"][0]["fill"], "#ff0000")

    @patch("apps.designs.views.suggest_design_candidates")
    def test_scope_color_preservation_violation_returns_503(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "color",
            "message": "Bad color suggestion.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Bad Option",
                    "description": "Adds object",
                    "patches": [{"blytzId": "missing-id", "property": "fill", "value": "#ff0000"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Bad Option 2",
                    "description": "Adds object 2",
                    "patches": [{"blytzId": "missing-id", "property": "fill", "value": "#ff0000"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change colors to red", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["code"], "ai_scope_violation")

    @patch("apps.designs.views.suggest_design_candidates")
    def test_scope_color_identical_candidates_returns_two(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "color",
            "message": "Identical color suggestions.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Option 1",
                    "description": "Red fill",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Option 2",
                    "description": "Red fill",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change colors to red", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        self.assertEqual(data["suggestions"][0]["canvasJSON"], data["suggestions"][1]["canvasJSON"])

    @patch("apps.designs.views.suggest_design_candidates")
    def test_color_scope_validates_against_actual_garment_not_tee(self, mock_suggest):
        self.design.garment_template = "hoodie"
        self.design.save()
        self.design.canvas_json = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [
                    {"type": "Rect", "blytzId": "obj-1", "left": 150, "top": 200, "width": 100, "height": 100, "fill": "#000"}
                ]
            }
        }
        self.design.save()

        mock_suggest.return_value = {
            "scope": "color",
            "message": "Change color",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Option 1",
                    "description": "Red",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Option 2",
                    "description": "Blue",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#0000ff"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change color to red", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)


@override_settings(GEMINI_API_KEY="test-key")
class AISuggestScopeStage1BTests(TestCase):
    def setUp(self):
        cache.clear()
        from django.contrib.auth import get_user_model
        from apps.designs.models import Design
        User = get_user_model()
        self.user = User.objects.create_user(
            email="scope1b-test@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.client.force_login(self.user)
        self.design = Design.objects.create(
            owner=self.user,
            title="Test Design 1B",
            garment_template="tee",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {
                    "version": "6.6.1",
                    "objects": [
                        {"type": "IText", "blytzId": "t1", "left": 250, "top": 250, "width": 200, "height": 36, "text": "OLD TEXT", "fill": "#000"},
                        {"type": "Rect", "blytzId": "r1", "left": 250, "top": 350, "width": 100, "height": 100, "fill": "#111"},
                    ]
                }
            }
        )
        self.url = reverse("design_ai_suggest", args=[self.design.pk])

    def test_detect_scope_change_text_returns_text(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("change the text to BLYTZ"), "text")

    def test_detect_scope_make_it_say_returns_text(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("make it say HELLO WORLD"), "text")

    def test_detect_scope_mixed_text_and_color_returns_redesign(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("change the text and the colors"), "redesign")

    def test_detect_scope_text_plus_redesign_cue_returns_redesign(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("redesign the text completely"), "redesign")

    def test_normalize_patch_candidates_text_scope_allows_text_property(self):
        from services.ai_design import _normalize_patch_candidates
        payload = {
            "candidates": [
                {
                    "id": "candidate-a",
                    "label": "Opt 1",
                    "description": "Desc 1",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Opt 2",
                    "description": "Desc 2",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ"}],
                },
            ]
        }
        res = _normalize_patch_candidates(payload, original_canvas_json=self.design.canvas_json, scope="text")
        self.assertEqual(len(res), 2)

    def test_normalize_patch_candidates_text_scope_rejects_non_text_object(self):
        from services.ai_design import _normalize_patch_candidates, AIDesignError
        payload = {
            "candidates": [
                {
                    "id": "candidate-a",
                    "label": "Opt 1",
                    "description": "Desc 1",
                    "patches": [{"blytzId": "r1", "property": "text", "value": "BLYTZ"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Opt 2",
                    "description": "Desc 2",
                    "patches": [{"blytzId": "r1", "property": "text", "value": "BLYTZ"}],
                },
            ]
        }
        with self.assertRaises(AIDesignError):
            _normalize_patch_candidates(payload, original_canvas_json=self.design.canvas_json, scope="text")

    def test_normalize_patch_candidates_color_scope_rejects_text_property(self):
        from services.ai_design import _normalize_patch_candidates, AIDesignError
        payload = {
            "candidates": [
                {
                    "id": "candidate-a",
                    "label": "Opt 1",
                    "description": "Desc 1",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Opt 2",
                    "description": "Desc 2",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ"}],
                },
            ]
        }
        with self.assertRaises(AIDesignError):
            _normalize_patch_candidates(payload, original_canvas_json=self.design.canvas_json, scope="color")

    def test_validate_preservation_text_passes_clean_text_change(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "t1", "property": "text", "value": "NEW"}]
        patched = apply_patches(canvas, patches)
        res = validate_preservation("text", canvas, patched, patches)
        self.assertIsNone(res)

    def test_validate_preservation_text_rejects_structural_change(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "t1", "property": "text", "value": "NEW"}]
        patched = apply_patches(canvas, patches)
        patched["canvas"]["objects"][0]["left"] = 999
        with self.assertRaises(ValueError):
            validate_preservation("text", canvas, patched, patches)

    def test_validate_preservation_text_rejects_untargeted_object_change(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "t1", "property": "text", "value": "NEW"}]
        patched = apply_patches(canvas, patches)
        patched["canvas"]["objects"][1]["fill"] = "#ffffff"
        with self.assertRaises(ValueError):
            validate_preservation("text", canvas, patched, patches)

    def test_validate_preservation_text_rejects_disallowed_property(self):
        from apps.designs.ai_suggest import apply_patches, validate_preservation
        canvas = self.design.canvas_json
        patches = [{"blytzId": "t1", "property": "width", "value": 999}]
        patched = apply_patches(canvas, patches)
        with self.assertRaises(ValueError):
            validate_preservation("text", canvas, patched, patches)

    @patch("apps.designs.views.suggest_design_candidates")
    def test_text_scope_finalizes_to_full_canvas(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "text",
            "message": "Updated text.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Option 1",
                    "description": "Text update",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ ONE"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Option 2",
                    "description": "Text update",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ TWO"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change the text to BLYTZ", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        sug0 = data["suggestions"][0]["canvasJSON"]
        self.assertEqual(len(sug0["canvas"]["objects"]), 2)
        self.assertEqual(sug0["canvas"]["objects"][0]["text"], "BLYTZ ONE")

    @patch("apps.designs.views.suggest_design_candidates")
    def test_text_scope_preservation_violation_returns_503(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "text",
            "message": "Bad text suggestion.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Bad Option",
                    "description": "Removes object",
                    "patches": [{"blytzId": "missing-id", "property": "text", "value": "BLYTZ"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Bad Option 2",
                    "description": "Removes object 2",
                    "patches": [{"blytzId": "missing-id", "property": "text", "value": "BLYTZ"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change the text to BLYTZ", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["code"], "ai_scope_violation")

    @patch("apps.designs.views.suggest_design_candidates")
    def test_text_scope_identical_candidates_returns_two(self, mock_suggest):
        mock_suggest.return_value = {
            "scope": "text",
            "message": "Identical text suggestions.",
            "suggestions": [
                {
                    "id": "candidate-a",
                    "label": "Option 1",
                    "description": "Text update",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ"}],
                },
                {
                    "id": "candidate-b",
                    "label": "Option 2",
                    "description": "Text update",
                    "patches": [{"blytzId": "t1", "property": "text", "value": "BLYTZ"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({"message": "change the text to BLYTZ", "active_side": "front", "canvas_json": self.design.canvas_json}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        self.assertEqual(data["suggestions"][0]["canvasJSON"], data["suggestions"][1]["canvasJSON"])


class AISuggestStage2VisionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="visionuser@example.com", password="password", role=User.Role.CUSTOMER)
        self.client.force_login(self.user)
        self.design = Design.objects.create(
            owner=self.user,
            title="Vision Test Design",
            garment_template="tee",
            garment_color="white",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {
                    "version": "6.6.1",
                    "objects": [
                        {
                            "type": "Rect",
                            "blytzId": "obj-1",
                            "left": 300,
                            "top": 280,
                            "width": 100,
                            "height": 100,
                            "fill": "#000",
                        }
                    ],
                },
            },
        )
        self.url = reverse("design_ai_suggest", kwargs={"pk": self.design.pk})

    def test_validate_reference_image_rejects_non_dict(self):
        with self.assertRaises(AISuggestValidationError):
            validate_reference_image("not-a-dict")

    def test_validate_reference_image_rejects_bad_mime(self):
        with self.assertRaises(AISuggestValidationError):
            validate_reference_image({"data": "Zm9v", "mime_type": "image/gif"})

    def test_validate_reference_image_rejects_oversized_base64(self):
        big_data = base64.b64encode(b"A" * (6 * 1024 * 1024)).decode("ascii")
        with self.assertRaises(AISuggestValidationError):
            validate_reference_image({"data": big_data, "mime_type": "image/png"})

    def test_validate_reference_image_rejects_magic_byte_mismatch(self):
        jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 100
        data = base64.b64encode(jpeg_bytes).decode("ascii")
        with self.assertRaises(AISuggestValidationError):
            validate_reference_image({"data": data, "mime_type": "image/png"})

    def _make_valid_image_data(self, fmt="PNG"):
        from PIL import Image
        import io
        img = Image.new("RGB", (10, 10), color="red")
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def test_validate_reference_image_accepts_valid_png(self):
        data = self._make_valid_image_data("PNG")
        res = validate_reference_image({"data": data, "mime_type": "image/png"})
        self.assertEqual(res["mime_type"], "image/png")

    def test_validate_reference_image_accepts_valid_jpeg(self):
        data = self._make_valid_image_data("JPEG")
        res = validate_reference_image({"data": data, "mime_type": "image/jpeg"})
        self.assertEqual(res["mime_type"], "image/jpeg")

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="")
    def test_vision_configured_false_when_no_gemini_key(self):
        self.assertFalse(vision_configured())

    @override_settings(AI_DESIGN_PROVIDER="openai", OPENAI_API_KEY="dummy")
    def test_vision_configured_false_when_provider_is_openai(self):
        self.assertFalse(vision_configured())

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="dummy")
    def test_vision_configured_true_when_gemini_key_and_provider(self):
        self.assertTrue(vision_configured())

    def test_detect_scope_use_this_font_returns_text(self):
        self.assertEqual(detect_scope("use this font from the reference"), "text")

    def test_detect_scope_typeface_returns_text(self):
        self.assertEqual(detect_scope("change the typeface to match"), "text")

    @override_settings(AI_DESIGN_PROVIDER="cerebras", CEREBRAS_API_KEY="dummy")
    @patch("apps.designs.views.vision_configured", return_value=False)
    def test_view_rejects_image_when_vision_disabled(self, mock_vision):
        response = self.client.post(
            self.url,
            json.dumps({
                "message": "test",
                "reference_image": {"data": "Zm9v", "mime_type": "image/png"}
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "ai_validation")

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="dummy")
    @patch("apps.designs.views.vision_configured", return_value=True)
    def test_view_rejects_invalid_image_when_vision_enabled(self, mock_vision):
        response = self.client.post(
            self.url,
            json.dumps({
                "message": "test",
                "reference_image": {"data": "Zm9v", "mime_type": "image/gif"}
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "bad_request")

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="dummy")
    @patch("apps.designs.views.vision_configured", return_value=True)
    @patch("apps.designs.views.suggest_design_candidates")
    def test_view_passes_reference_image_to_suggest(self, mock_suggest, mock_vision):
        b64 = self._make_valid_image_data("PNG")
        mock_suggest.return_value = {
            "message": "Here are designs",
            "suggestions": [
                {
                    "id": "c1",
                    "label": "Option 1",
                    "description": "Desc 1",
                    "canvasJSON": VALID_CANDIDATE_A,
                },
                {
                    "id": "c2",
                    "label": "Option 2",
                    "description": "Desc 2",
                    "canvasJSON": VALID_CANDIDATE_A,
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({
                "message": "redesign",
                "reference_image": {"data": b64, "mime_type": "image/png"}
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        mock_suggest.assert_called_once()
        _, kwargs = mock_suggest.call_args
        self.assertIsNotNone(kwargs.get("reference_image"))
        self.assertEqual(kwargs["reference_image"]["mime_type"], "image/png")

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="dummy")
    @patch("apps.designs.views.vision_configured", return_value=True)
    @patch("apps.designs.views.suggest_design_candidates")
    def test_view_passes_none_when_no_image(self, mock_suggest, mock_vision):
        mock_suggest.return_value = {
            "message": "Here are designs",
            "suggestions": [
                {
                    "id": "c1",
                    "label": "Option 1",
                    "description": "Desc 1",
                    "canvasJSON": VALID_CANDIDATE_A,
                },
                {
                    "id": "c2",
                    "label": "Option 2",
                    "description": "Desc 2",
                    "canvasJSON": VALID_CANDIDATE_A,
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({
                "message": "redesign"
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        mock_suggest.assert_called_once()
        _, kwargs = mock_suggest.call_args
        self.assertIsNone(kwargs.get("reference_image"))

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="dummy")
    @patch("apps.designs.views.vision_configured", return_value=True)
    @patch("apps.designs.views.suggest_design_candidates")
    def test_image_with_color_scope_preserves_object_count(self, mock_suggest, mock_vision):
        b64 = self._make_valid_image_data("PNG")
        mock_suggest.return_value = {
            "scope": "color",
            "message": "Color adjustment",
            "suggestions": [
                {
                    "id": "c1",
                    "label": "Option 1",
                    "description": "Red",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}],
                },
                {
                    "id": "c2",
                    "label": "Option 2",
                    "description": "Red",
                    "patches": [{"blytzId": "obj-1", "property": "fill", "value": "#ff0000"}],
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({
                "message": "use these colors",
                "canvas_json": self.design.canvas_json,
                "reference_image": {"data": b64, "mime_type": "image/png"}
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        self.assertEqual(len(data["suggestions"][0]["canvasJSON"]["canvas"]["objects"]), 1)

    @override_settings(AI_DESIGN_PROVIDER="gemini", GEMINI_API_KEY="dummy")
    @patch("apps.designs.views.vision_configured", return_value=True)
    @patch("apps.designs.views.suggest_design_candidates")
    def test_image_with_redesign_scope_returns_full_canvas(self, mock_suggest, mock_vision):
        b64 = self._make_valid_image_data("PNG")
        mock_suggest.return_value = {
            "scope": "redesign",
            "message": "Redesign",
            "suggestions": [
                {
                    "id": "c1",
                    "label": "Option 1",
                    "description": "Desc 1",
                    "canvasJSON": VALID_CANDIDATE_A,
                },
                {
                    "id": "c2",
                    "label": "Option 2",
                    "description": "Desc 2",
                    "canvasJSON": VALID_CANDIDATE_A,
                },
            ]
        }
        response = self.client.post(
            self.url,
            json.dumps({
                "message": "redesign inspired by this",
                "reference_image": {"data": b64, "mime_type": "image/png"}
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        self.assertIn("canvasJSON", data["suggestions"][0])

    @override_settings(AI_DESIGN_PROVIDER="groq", GROQ_API_KEY="dummy")
    def test_groq_rejects_image_input(self):
        with self.assertRaises(AIDesignError) as ctx:
            suggest_design_candidates(
                message="test",
                canvas_json=self.design.canvas_json,
                active_side="front",
                reference_image={"data": "Zm9v", "mime_type": "image/png"}
            )
        self.assertEqual(ctx.exception.code, "ai_validation")

    @override_settings(AI_DESIGN_PROVIDER="cerebras", CEREBRAS_API_KEY="dummy")
    def test_cerebras_rejects_image_input(self):
        with self.assertRaises(AIDesignError) as ctx:
            suggest_design_candidates(
                message="test",
                canvas_json=self.design.canvas_json,
                active_side="front",
                reference_image={"data": "Zm9v", "mime_type": "image/png"}
            )
        self.assertEqual(ctx.exception.code, "ai_validation")


class AISuggestElementScopeTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="element-customer@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Element test design",
            garment_template="tee",
            garment_color="white",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {
                    "version": "6.6.1",
                    "objects": [
                        {
                            "type": "Circle",
                            "left": 300,
                            "top": 300,
                            "width": 100,
                            "height": 100,
                            "fill": "#ff0000",
                            "blytzId": "obj-circle",
                        },
                        {
                            "type": "Rect",
                            "left": 450,
                            "top": 300,
                            "width": 80,
                            "height": 80,
                            "fill": "#00ff00",
                            "blytzId": "obj-rect",
                        }
                    ],
                },
            },
        )
        self.url = reverse("design_ai_suggest", args=[self.design.pk])

    def test_detect_scope_element_returns_element(self):
        from apps.designs.ai_suggest import detect_scope
        self.assertEqual(detect_scope("change the design in the middle"), "element")
        self.assertEqual(detect_scope("replace the circle with a heart"), "element")
        self.assertEqual(detect_scope("swap the logo"), "element")

    def test_element_remove_object(self):
        from apps.designs.ai_suggest import apply_element_patches
        patches = [{"action": "remove", "blytzId": "obj-circle"}]
        patched = apply_element_patches(self.design.canvas_json, patches)
        objs = patched["canvas"]["objects"]
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]["blytzId"], "obj-rect")

    def test_element_replace_object(self):
        from apps.designs.ai_suggest import apply_element_patches
        new_obj = {
            "type": "path",
            "left": 300,
            "top": 300,
            "width": 100,
            "height": 100,
            "fill": "#0000ff",
        }
        patches = [{"action": "replace", "blytzId": "obj-circle", "object": new_obj}]
        patched = apply_element_patches(self.design.canvas_json, patches)
        objs = patched["canvas"]["objects"]
        self.assertEqual(len(objs), 2)
        self.assertFalse(any(o.get("blytzId") == "obj-circle" for o in objs))
        replaced = next(o for o in objs if o.get("type") == "path")
        self.assertEqual(replaced["fill"], "#0000ff")

    def test_element_preserves_untargeted(self):
        from apps.designs.ai_suggest import apply_element_patches, validate_element_preservation
        new_obj = {
            "type": "path",
            "left": 300,
            "top": 300,
            "width": 100,
            "height": 100,
            "fill": "#0000ff",
        }
        patches = [{"action": "replace", "blytzId": "obj-circle", "object": new_obj}]
        patched = apply_element_patches(self.design.canvas_json, patches)
        validate_element_preservation(self.design.canvas_json, patched, patches)

        orig_rect = next(o for o in self.design.canvas_json["canvas"]["objects"] if o.get("blytzId") == "obj-rect")
        patched_rect = next(o for o in patched["canvas"]["objects"] if o.get("blytzId") == "obj-rect")
        self.assertEqual(orig_rect, patched_rect)

    @patch("apps.designs.views.suggest_design_candidates")
    def test_element_view_returns_full_canvas(self, mock_suggest):
        new_obj = {
            "type": "circle",
            "left": 320,
            "top": 320,
            "width": 80,
            "height": 80,
            "fill": "#ff00ff",
            "blytzId": "obj-new",
        }
        mock_suggest.return_value = {
            "message": "Replaced element",
            "scope": "element",
            "suggestions": [
                {
                    "id": "a",
                    "label": "Option A",
                    "description": "Desc A",
                    "patches": [{"action": "replace", "blytzId": "obj-circle", "object": new_obj}],
                },
                {
                    "id": "b",
                    "label": "Option B",
                    "description": "Desc B",
                    "patches": [{"action": "remove", "blytzId": "obj-circle"}],
                },
            ],
            "usage": {"prompt_tokens": 10, "output_tokens": 20},
        }
        self.client.force_login(self.customer)
        response = self.client.post(
            self.url,
            data=json.dumps({
                "message": "replace the circle",
                "canvas_json": self.design.canvas_json,
                "active_side": "front",
            }),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["suggestions"]), 2)
        sug_a = data["suggestions"][0]
        self.assertEqual(sug_a["canvasJSON"]["schema_version"], 1)
        objs = sug_a["canvasJSON"]["canvas"]["objects"]
        self.assertTrue(any(o.get("blytzId") == "obj-new" for o in objs))

    def test_element_preserves_bounds(self):
        from apps.designs.ai_suggest import apply_element_patches, assert_envelope_in_print_bounds
        new_obj = {
            "type": "circle",
            "left": 320,
            "top": 320,
            "width": 80,
            "height": 80,
            "fill": "#ff00ff",
        }
        patches = [{"action": "replace", "blytzId": "obj-circle", "object": new_obj}]
        patched = apply_element_patches(self.design.canvas_json, patches)
        env = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": patched["canvas"],
        }
        assert_envelope_in_print_bounds(env, garment_template="tee", side="front")
                
    @override_settings(
        AI_DESIGN_PROVIDER="deepseek",
        DEEPSEEK_API_KEY="dummy",
        DEEPSEEK_BASE_URL="https://example.invalid/v1",
    )
    def test_deepseek_element_uses_patch_normalizer(self):
        """Regression: _call_openai_compatible must route element scope to
        _normalize_patch_candidates, not _normalize_candidates."""
        from services.ai_design import suggest_design_candidates

        patch_response = {
            "message": "Replaced the circle with a heart",
            "candidates": [
                {
                    "id": "candidate-a",
                    "label": "Heart A",
                    "description": "Path heart",
                    "patches": [
                        {
                            "action": "replace",
                            "blytzId": "obj-circle",
                            "object": {
                                "type": "path",
                                "path": [["M", 0, 0], ["Z"]],
                                "left": 300,
                                "top": 300,
                                "width": 100,
                                "height": 100,
                                "fill": "#ff0000",
                            },
                        }
                    ],
                },
                {
                    "id": "candidate-b",
                    "label": "Heart B",
                    "description": "Alt heart",
                    "patches": [
                        {
                            "action": "replace",
                            "blytzId": "obj-circle",
                            "object": {
                                "type": "path",
                                "path": [["M", 0, 0], ["Z"]],
                                "left": 300,
                                "top": 300,
                                "width": 100,
                                "height": 100,
                                "fill": "#00ff00",
                            },
                        }
                    ],
                },
            ],
        }
        mock_body = json.dumps({
            "choices": [
                {
                    "message": {"content": json.dumps(patch_response)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        })

        class _Resp:
            status = 200
            def __init__(self, body):
                self._body = body
            def read(self):
                return self._body.encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        with patch("services.ai_design.urllib.request.urlopen", return_value=_Resp(mock_body)):
            result = suggest_design_candidates(
                message="change the design in the middle to match the image attached",
                canvas_json=self.design.canvas_json,
                active_side="front",
                scope="element",
            )

        self.assertEqual(result["scope"], "element")
        self.assertEqual(len(result["suggestions"]), 2)
        self.assertIn("patches", result["suggestions"][0])
        self.assertEqual(result["suggestions"][0]["patches"][0]["action"], "replace")

