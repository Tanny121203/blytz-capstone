"""BEHAVIOR and SOURCE-STRING tests for garment fields and B1 views (Stage 3d+3e)."""

import json

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.designs.forms import DesignSaveForm, MAX_CANVAS_JSON_BYTES
from apps.designs.models import Design

User = get_user_model()


def _v1_envelope(front_objects=None, back_objects=None, include_views=True):
    env = {
        "schema_version": 1,
        "width": 800,
        "height": 800,
        "canvas": {
            "version": "6.6.1",
            "objects": front_objects
            if front_objects is not None
            else [{"type": "Rect", "blytzId": "f1", "left": 10, "top": 10}],
        },
    }
    if include_views:
        env["views"] = {
            "back": {
                "version": "6.6.1",
                "objects": back_objects
                if back_objects is not None
                else [{"type": "Ellipse", "blytzId": "b1", "left": 20, "top": 20}],
            }
        }
    return env


class GarmentFieldsBehaviorTests(TestCase):
    """BEHAVIOR: garment_template / garment_color save semantics."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="garment@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.user,
            title="Garment design",
            garment_template="tee",
            garment_color="black",
            canvas_json=_v1_envelope(),
        )
        self.client.force_login(self.user)

    def test_save_valid_garment_persists_and_editor_renders_data_attrs(self):
        """BEHAVIOR"""
        payload = _v1_envelope()
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {
                "canvas_json": json.dumps(payload),
                "garment_template": "hoodie",
                "garment_color": "navy",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.design.refresh_from_db()
        self.assertEqual(self.design.garment_template, "hoodie")
        self.assertEqual(self.design.garment_color, "navy")
        editor = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(editor.status_code, 200)
        html = editor.content.decode("utf-8")
        self.assertIn('data-garment-template="hoodie"', html)
        self.assertIn('data-garment-color="navy"', html)

    def test_invalid_template_rejected_nothing_saved(self):
        """BEHAVIOR"""
        before_t = self.design.garment_template
        before_c = self.design.garment_color
        before_canvas = self.design.canvas_json
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {
                "canvas_json": json.dumps(_v1_envelope()),
                "garment_template": "evil",
                "garment_color": "navy",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 400)
        self.design.refresh_from_db()
        self.assertEqual(self.design.garment_template, before_t)
        self.assertEqual(self.design.garment_color, before_c)
        self.assertEqual(self.design.canvas_json, before_canvas)

    def test_invalid_color_rejected_nothing_saved(self):
        """BEHAVIOR"""
        before_t = self.design.garment_template
        before_c = self.design.garment_color
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {
                "canvas_json": json.dumps(_v1_envelope()),
                "garment_template": "tee",
                "garment_color": "hotpink",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 400)
        self.design.refresh_from_db()
        self.assertEqual(self.design.garment_template, before_t)
        self.assertEqual(self.design.garment_color, before_c)

    def test_absent_garment_fields_leave_stored_unchanged(self):
        """BEHAVIOR"""
        self.design.garment_template = "polo"
        self.design.garment_color = "red"
        self.design.save(update_fields=["garment_template", "garment_color"])
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(_v1_envelope())},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.design.refresh_from_db()
        self.assertEqual(self.design.garment_template, "polo")
        self.assertEqual(self.design.garment_color, "red")

    def test_legacy_save_without_garment_fields_still_works(self):
        """BEHAVIOR"""
        form = DesignSaveForm(
            data={"canvas_json": json.dumps(_v1_envelope())},
            stored_canvas=self.design.canvas_json,
        )
        self.assertTrue(form.is_valid(), form.errors)


class ViewsEnvelopeBehaviorTests(TestCase):
    """BEHAVIOR: views.back persistence, stale-client guard, safety, size cap."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="views@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="views-other@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.user,
            title="Views design",
            garment_template="tee",
            garment_color="black",
            canvas_json=_v1_envelope(),
        )
        self.client.force_login(self.user)

    def test_save_with_views_back_persists_both_and_reload_returns_both(self):
        """BEHAVIOR"""
        payload = _v1_envelope(
            front_objects=[{"type": "Rect", "blytzId": "frontA"}],
            back_objects=[{"type": "IText", "text": "back", "blytzId": "backA"}],
        )
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(payload)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.design.refresh_from_db()
        stored = self.design.canvas_json
        self.assertEqual(stored["canvas"]["objects"][0]["blytzId"], "frontA")
        self.assertEqual(stored["views"]["back"]["objects"][0]["blytzId"], "backA")
        editor = self.client.get(reverse("design_editor", args=[self.design.pk]))
        initial = json.loads(editor.context["canvas_json_initial"])
        self.assertEqual(initial["canvas"]["objects"][0]["blytzId"], "frontA")
        self.assertEqual(initial["views"]["back"]["objects"][0]["blytzId"], "backA")

    def test_stale_client_guard_keeps_stored_back_when_views_omitted(self):
        """BEHAVIOR"""
        self.design.canvas_json = _v1_envelope(
            back_objects=[{"type": "Rect", "blytzId": "keep-me"}]
        )
        self.design.save(update_fields=["canvas_json"])
        incoming = _v1_envelope(include_views=False)
        incoming["canvas"]["objects"] = [{"type": "Rect", "blytzId": "new-front"}]
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(incoming)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.design.refresh_from_db()
        self.assertEqual(
            self.design.canvas_json["views"]["back"]["objects"][0]["blytzId"],
            "keep-me",
        )
        self.assertEqual(
            self.design.canvas_json["canvas"]["objects"][0]["blytzId"], "new-front"
        )

    def test_explicit_empty_views_clears_back(self):
        """BEHAVIOR"""
        self.design.canvas_json = _v1_envelope(
            back_objects=[{"type": "Rect", "blytzId": "gone"}]
        )
        self.design.save(update_fields=["canvas_json"])
        incoming = _v1_envelope(back_objects=[])
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(incoming)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.design.refresh_from_db()
        self.assertEqual(self.design.canvas_json["views"]["back"]["objects"], [])

    def test_views_front_rejected(self):
        """BEHAVIOR"""
        payload = _v1_envelope()
        payload["views"]["front"] = {"objects": []}
        form = DesignSaveForm(
            data={"canvas_json": json.dumps(payload)},
            stored_canvas=self.design.canvas_json,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("canvas_json", form.errors)

    def test_unknown_views_key_rejected(self):
        """BEHAVIOR"""
        payload = _v1_envelope()
        payload["views"]["sleeve"] = {"objects": []}
        form = DesignSaveForm(
            data={"canvas_json": json.dumps(payload)},
            stored_canvas=self.design.canvas_json,
        )
        self.assertFalse(form.is_valid())

    def test_views_back_external_image_rejected(self):
        """BEHAVIOR"""
        payload = _v1_envelope(
            back_objects=[
                {
                    "type": "Image",
                    "src": "https://evil.example/x.png",
                    "blytzId": "bad",
                }
            ]
        )
        form = DesignSaveForm(
            data={"canvas_json": json.dumps(payload)},
            stored_canvas=self.design.canvas_json,
        )
        self.assertFalse(form.is_valid())

    def test_non_v1_payload_stays_untouched(self):
        """BEHAVIOR"""
        payload = {"schema_version": 99, "blob": "x" * 100}
        form = DesignSaveForm(
            data={"canvas_json": json.dumps(payload)},
            stored_canvas={"schema_version": 99, "blob": "old"},
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["canvas_json"]["schema_version"], 99)
        self.assertNotIn("views", form.cleaned_data["canvas_json"])

    def test_whole_envelope_2mib_cap_counts_both_views(self):
        """BEHAVIOR"""
        # Each view under 2 MiB alone, combined over the cap.
        half = (MAX_CANVAS_JSON_BYTES // 2) + 50_000
        pad_a = "a" * half
        pad_b = "b" * half
        payload = {
            "schema_version": 1,
            "width": 800,
            "height": 800,
            "canvas": {
                "version": "6.6.1",
                "objects": [{"type": "Rect", "blytzId": "a", "pad": pad_a}],
            },
            "views": {
                "back": {
                    "version": "6.6.1",
                    "objects": [{"type": "Rect", "blytzId": "b", "pad": pad_b}],
                }
            },
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.assertGreater(len(encoded.encode("utf-8")), MAX_CANVAS_JSON_BYTES)
        # Per-view rough check: canvas-only stringify under cap.
        front_only = json.dumps(payload["canvas"], separators=(",", ":"))
        back_only = json.dumps(payload["views"]["back"], separators=(",", ":"))
        self.assertLess(len(front_only.encode("utf-8")), MAX_CANVAS_JSON_BYTES)
        self.assertLess(len(back_only.encode("utf-8")), MAX_CANVAS_JSON_BYTES)
        form = DesignSaveForm(data={"canvas_json": encoded})
        self.assertFalse(form.is_valid())
        self.assertIn("canvas_json", form.errors)

    def test_other_user_cannot_save(self):
        """BEHAVIOR: ownership"""
        self.client.force_login(self.other)
        resp = self.client.post(
            reverse("design_save", args=[self.design.pk]),
            {"canvas_json": json.dumps(_v1_envelope())},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertIn(resp.status_code, (403, 404))
        self.design.refresh_from_db()
        self.assertEqual(
            self.design.canvas_json["canvas"]["objects"][0].get("blytzId"), "f1"
        )


class GarmentViewsSourceStringTests(TestCase):
    """SOURCE-STRING: garment/view constants and public API names."""

    def test_js_garment_and_view_api_names(self):
        """SOURCE-STRING"""
        canvas_path = finders.find("js/editor_canvas.js")
        self.assertIsNotNone(canvas_path)
        with open(canvas_path, encoding="utf-8") as fh:
            canvas_src = fh.read()
        for token in (
            "getActiveView",
            "setActiveView",
            "getActiveCanvasJSON",
            "onViewChange",
            "getGarmentState",
            "setGarmentState",
            "onGarmentChange",
            "views.back",
            "loadAllViewsFromEnvelope",
            "getExportLayerMarkups",
            "artworkDataURLFromPayload",
            "compositeUnderArtOver",
            "includeGarment",
            "StaticCanvas",
            "PREVIEW_MAX_BYTES",
        ):
            self.assertIn(token, canvas_src)

        garments_path = finders.find("js/editor_garments.js")
        self.assertIsNotNone(garments_path)
        with open(garments_path, encoding="utf-8") as fh:
            g_src = fh.read()
        for token in (
            "GARMENT_TYPES",
            "GARMENT_COLORS",
            "GARMENT_TEMPLATE_ALIASES",
            "VIEW_IDS",
            "contrastColor",
            "renderGarmentLayer",
            "splitGarmentSvg",
            "editor-garment-overlay",
            "--garment",
            "--trim",
            "--string",
            "data-blytz-lite-garment",
            "resolveSvgCssVars",
            "getExportLayerMarkups",
            "SVG_VAR_TRIM",
            "var(--trim, var(--garment, #f2f2ef))",
            "var(--garment, #f2f2ef)",
            "var(--string, #e9e5da)",
            "EXPORT_GRAIN_OPACITY",
            "lowerExportGrainOpacity",
        ):
            self.assertIn(token, g_src)

        from pathlib import Path

        choices = Path(__file__).resolve().parents[1] / "garment_choices.py"
        text = choices.read_text(encoding="utf-8")
        self.assertIn("editor_garments.js", text)
        self.assertIn("apply_stale_client_views_guard", text)
        self.assertIn("GARMENT_TEMPLATE_ALIASES", text)
        self.assertIn("tee", text)
        self.assertIn("hoodie", text)
        self.assertIn("polo", text)
        self.assertIn("jersey", text)


class GarmentAssetAndAllowListTests(TestCase):
    """BEHAVIOR/SOURCE: new garment assets, allow-lists, aliases."""

    def test_python_and_js_template_ids_identical(self):
        """SOURCE-STRING: Python allow-list matches JS GARMENT_TYPES ids + order."""
        from apps.designs.garment_choices import GARMENT_TEMPLATE_IDS

        garments_path = finders.find("js/editor_garments.js")
        self.assertIsNotNone(garments_path)
        with open(garments_path, encoding="utf-8") as fh:
            g_src = fh.read()
        # Top-level garment entries: six-space indent before id: (print-area ids nest deeper).
        start = g_src.index("var GARMENT_TYPES = [")
        end = g_src.index("];", start)
        block = g_src[start:end]
        import re

        ids = re.findall(r'^ {6}id:\s*"([a-z]+)"', block, flags=re.M)
        self.assertEqual(tuple(ids), GARMENT_TEMPLATE_IDS)
        self.assertEqual(GARMENT_TEMPLATE_IDS, ("tee", "polo", "hoodie", "jersey"))

    def test_all_eight_garment_svg_assets_exist(self):
        """BEHAVIOR: tee/polo/hoodie/jersey × front/back SVG files are served."""
        from pathlib import Path

        for garment in ("tee", "polo", "hoodie", "jersey"):
            for view in ("front", "back"):
                path = finders.find(f"garments/{garment}-{view}.svg")
                self.assertIsNotNone(path, f"missing {garment}-{view}.svg")
                text = Path(path).read_text(encoding="utf-8")
                prefix = f"{garment}-{view}-"
                for suffix in ("ground", "base", "art", "details", "shade"):
                    self.assertIn(f'id="{prefix}{suffix}"', text)

    def test_garments_json_print_areas_match_js(self):
        """SOURCE-STRING: garments.json exists and lists print areas for each view."""
        import json
        from pathlib import Path

        path = finders.find("garments/garments.json")
        self.assertIsNotNone(path)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key in ("tee", "polo", "hoodie", "jersey"):
            self.assertIn(key, data)
            self.assertIn("label", data[key])
            for view in ("front", "back"):
                areas = data[key]["views"][view]["printAreas"]
                self.assertIsInstance(areas, list)
                self.assertGreater(len(areas), 0)

    def test_normalize_garment_template_aliases(self):
        """BEHAVIOR: aliases map to canonical keys; unknown rejected."""
        from apps.designs.garment_choices import normalize_garment_template

        self.assertEqual(normalize_garment_template("tee"), "tee")
        self.assertEqual(normalize_garment_template("t-shirt"), "tee")
        self.assertEqual(normalize_garment_template("Tshirt"), "tee")
        self.assertEqual(normalize_garment_template("sweatshirt"), "hoodie")
        self.assertIsNone(normalize_garment_template("evil"))
        self.assertIsNone(normalize_garment_template(""))

    def test_alias_rejected_on_save(self):
        """BEHAVIOR: server accepts only canonical ids, not aliases."""
        user = User.objects.create_user(
            email="alias-garment@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        design = Design.objects.create(
            owner=user,
            title="Alias design",
            garment_template="tee",
            garment_color="black",
            canvas_json=_v1_envelope(),
        )
        form = DesignSaveForm(
            data={
                "canvas_json": json.dumps(_v1_envelope()),
                "garment_template": "t-shirt",
            },
            stored_canvas=design.canvas_json,
        )
        self.assertFalse(form.is_valid())

    def test_data_migration_normalizes_stored_aliases(self):
        """BEHAVIOR: migration 0005 rewrites legacy alias keys."""
        import importlib

        from django.apps import apps

        mig = importlib.import_module(
            "apps.designs.migrations.0005_normalize_garment_templates"
        )

        user = User.objects.create_user(
            email="migrate-garment@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        design = Design.objects.create(
            owner=user,
            title="Legacy alias",
            garment_template="tee",
            garment_color="white",
            canvas_json={},
        )
        # Bypass choices validation to simulate pre-migration row.
        Design.objects.filter(pk=design.pk).update(garment_template="tshirt")
        design.refresh_from_db()
        self.assertEqual(design.garment_template, "tshirt")

        mig.forwards(apps, None)
        design.refresh_from_db()
        self.assertEqual(design.garment_template, "tee")

    def test_editor_exposes_garments_base(self):
        """BEHAVIOR: editor page includes static garments base for SVG fetch."""
        user = User.objects.create_user(
            email="garment-base@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        design = Design.objects.create(
            owner=user,
            title="Base path",
            garment_template="polo",
            garment_color="navy",
            canvas_json=_v1_envelope(),
        )
        self.client.force_login(user)
        resp = self.client.get(reverse("design_editor", args=[design.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("data-garments-base=", html)
        self.assertIn("garments/", html)
        # Leak guard: multi-line {# #} comments must not appear in rendered HTML.
        self.assertNotIn("Wrap size is set in JS", html)
        self.assertNotIn("max-w-[800px] may be absent", html)

    def test_svg_assets_use_expected_css_var_strings(self):
        """SOURCE-STRING: garment SVGs use the exact var(...) forms export bakes."""
        from pathlib import Path

        trim = "var(--trim, var(--garment, #f2f2ef))"
        garment = "var(--garment, #f2f2ef)"
        string = "var(--string, #e9e5da)"
        found_garment = False
        found_trim = False
        found_string = False
        for garment_id in ("tee", "polo", "hoodie", "jersey"):
            for view in ("front", "back"):
                path = finders.find(f"garments/{garment_id}-{view}.svg")
                self.assertIsNotNone(path)
                text = Path(path).read_text(encoding="utf-8")
                if garment in text:
                    found_garment = True
                if trim in text:
                    found_trim = True
                if string in text:
                    found_string = True
                # Bake with the same order as resolveSvgCssVars; no var( may remain.
                baked = (
                    text.replace(trim, "#ffffff")
                    .replace(garment, "#111111")
                    .replace(string, "#e9e5da")
                )
                self.assertNotIn(
                    "var(",
                    baked,
                    msg=f"unresolved var( in {garment_id}-{view} after bake",
                )
        self.assertTrue(found_garment)
        self.assertTrue(found_trim)
        self.assertTrue(found_string)

    def test_seed_demo_runs_with_canonical_garments(self):
        """BEHAVIOR: seed_demo completes and uses allow-listed garment keys."""
        from django.core.management import call_command

        from apps.designs.garment_choices import (
            GARMENT_COLOR_IDS,
            GARMENT_TEMPLATE_IDS,
        )

        call_command("seed_demo")
        for design in Design.objects.all():
            self.assertIn(design.garment_template, GARMENT_TEMPLATE_IDS)
            self.assertIn(design.garment_color, GARMENT_COLOR_IDS)
