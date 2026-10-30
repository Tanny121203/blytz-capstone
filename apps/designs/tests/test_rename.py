from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.designs.models import Design
from apps.orders.models import Order

User = get_user_model()


class DesignRenameTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="rename-owner@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            email="rename-other@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.draft = Design.objects.create(
            owner=self.owner,
            title="Draft title",
            canvas_json={"version": 1, "objects": []},
        )

    def _save(self, user, design, *, title=None, canvas='{"version":1,"objects":[]}'):
        self.client.force_login(user)
        data = {"canvas_json": canvas}
        if title is not None:
            data["title"] = title
        return self.client.post(
            reverse("design_save", args=[design.pk]),
            data,
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_rename_works_on_draft(self):
        response = self._save(self.owner, self.draft, title="  New name  ")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["title"], "New name")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "New name")

    def test_empty_title_becomes_untitled_design(self):
        response = self._save(self.owner, self.draft, title="   ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Untitled design")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "Untitled design")

    def test_rename_rejected_after_submission(self):
        Order.objects.create(
            customer=self.owner,
            design=self.draft,
            status=Order.Status.JOB_REQUEST,
        )
        response = self._save(self.owner, self.draft, title="Should fail")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "Draft title")

    def test_any_save_rejected_after_submission(self):
        Order.objects.create(
            customer=self.owner,
            design=self.draft,
            status=Order.Status.JOB_REQUEST,
        )
        response = self._save(
            self.owner,
            self.draft,
            canvas='{"version":1,"objects":[{"type":"rect"}]}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.canvas_json, {"version": 1, "objects": []})

    def test_another_customer_cannot_rename(self):
        response = self._save(self.other, self.draft, title="Hijacked")
        self.assertEqual(response.status_code, 404)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "Draft title")

    def test_editor_shows_editable_title_for_draft(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("design_editor", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="editor-design-title"')
        self.assertContains(response, "data-editor-title")

    def test_editor_title_readonly_after_submission(self):
        Order.objects.create(
            customer=self.owner,
            design=self.draft,
            status=Order.Status.JOB_REQUEST,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("design_editor", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="editor-design-title"')
        self.assertContains(response, self.draft.title)
