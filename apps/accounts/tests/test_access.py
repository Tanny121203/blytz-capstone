from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.adapters import AccountAdapter

User = get_user_model()


class RoleAccessTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="test-pass-123",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )

    def test_customer_gets_403_on_staff_urls(self):
        self.client.force_login(self.customer)
        staff_home = self.client.get(reverse("staff_home"))
        admin_only = self.client.get(reverse("staff_admin_only"))
        self.assertEqual(staff_home.status_code, 403)
        self.assertEqual(admin_only.status_code, 403)

    def test_staff_gets_403_on_admin_only_urls(self):
        self.client.force_login(self.staff)
        allowed = self.client.get(reverse("staff_home"))
        denied = self.client.get(reverse("staff_admin_only"))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_customer_can_access_app_home(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("app_home"))
        self.assertEqual(response.status_code, 200)

    def test_staff_gets_403_on_customer_app(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("app_home"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_admin_only(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff_admin_only"))
        self.assertEqual(response.status_code, 200)

    def test_login_redirects_customer_to_app(self):
        request = RequestFactory().get("/")
        request.user = self.customer
        self.assertEqual(
            AccountAdapter().get_login_redirect_url(request),
            reverse("app_home"),
        )

    def test_login_redirects_staff_and_admin_to_staff(self):
        adapter = AccountAdapter()
        request = RequestFactory().get("/")

        request.user = self.staff
        self.assertEqual(adapter.get_login_redirect_url(request), reverse("staff_home"))

        request.user = self.admin
        self.assertEqual(adapter.get_login_redirect_url(request), reverse("staff_home"))
