"""Stage R.2 — client-side background removal (no remove.bg server)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import Design

User = get_user_model()


class RemoveBgClientEditorTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="rbg2-customer@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.design = Design.objects.create(
            owner=self.customer,
            title="Client remove BG",
            garment_template="tee",
            garment_color="white",
            canvas_json={
                "schema_version": 1,
                "width": 800,
                "height": 800,
                "canvas": {"version": "6.6.1", "objects": []},
            },
        )

    def test_editor_loads_client_remove_bg_assets(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("design_editor", args=[self.design.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "remove_bg_client.js")
        self.assertContains(response, 'data-remove-bg-client="1"')
        self.assertNotContains(response, "data-remove-bg-url=")
        self.assertNotContains(response, "image/remove-bg/")

    def test_remove_bg_api_route_gone(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            f"/app/designs/{self.design.pk}/image/remove-bg/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
