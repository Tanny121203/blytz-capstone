from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class LandingAuthNavTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="landing-customer@example.com",
            password="test-pass-123",
            role=User.Role.CUSTOMER,
        )
        self.staff = User.objects.create_user(
            email="landing-staff@example.com",
            password="test-pass-123",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            email="landing-admin@example.com",
            password="test-pass-123",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )

    def test_logged_out_visitor_sees_landing(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How it works")
        self.assertContains(response, "Gallery")
        self.assertContains(response, "What customers say")
        self.assertContains(response, "FAQ")
        self.assertContains(response, 'id="contact"')

    def test_logged_in_customer_redirected_to_app(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("app_home"))

    def test_logged_in_staff_redirected_to_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("staff_home"))

    def test_logged_in_admin_redirected_to_staff(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("staff_home"))

    def test_customer_navbar_has_dashboard_not_home(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("app_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Customer"')
        self.assertNotContains(response, ">Home</a>")
        self.assertContains(response, ">Dashboard</a>")
        self.assertContains(response, f'href="{reverse("app_home")}"')
        self.assertNotContains(response, f'href="{reverse("home")}"')

    def test_skip_link_and_main_landmark(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("app_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="#main"')
        self.assertContains(response, "Skip to main content")
        self.assertContains(response, 'id="main"')
        self.assertContains(response, "blytz-skip-link")

    def test_logged_out_navbar_has_no_dashboard(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, ">Dashboard</a>")
        self.assertContains(response, "Log in")
        self.assertContains(response, "Sign up")

    def test_hero_button_targets_login_when_logged_out(self):
        logged_out = self.client.get(reverse("home"))
        self.assertContains(logged_out, 'href="/accounts/login/"')
        self.assertContains(logged_out, "Sign in to start designing")

    def test_staff_navbar_role_badge_from_user_role(self):
        self.client.force_login(self.staff)
        staff_resp = self.client.get(reverse("staff_home"))
        self.assertEqual(staff_resp.status_code, 200)
        self.assertContains(staff_resp, ">Staff</span>")
        self.assertNotContains(staff_resp, ">Admin</span>")

        self.client.force_login(self.admin)
        admin_resp = self.client.get(reverse("staff_home"))
        self.assertEqual(admin_resp.status_code, 200)
        self.assertContains(admin_resp, ">Admin</span>")
