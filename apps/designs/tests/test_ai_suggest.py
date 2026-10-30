"""Stage O — AI suggest endpoint (Gemini mocked)."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.designs.models import Design
from services.ai_design import AIDesignError

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

    @override_settings(GEMINI_API_KEY="")
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
            )

        self.assertEqual(len(result["suggestions"]), 2)
        req = mock_open.call_args[0][0]
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", req.full_url)
        self.assertNotIn("gemini-2.5-flash", req.full_url)
        self.assertNotIn("gemini-2.0-flash", req.full_url)
