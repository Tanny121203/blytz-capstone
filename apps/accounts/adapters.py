from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        if getattr(user, "is_staff_role", False):
            return reverse("staff_home")
        return reverse("app_home")

    def get_signup_redirect_url(self, request):
        # Mandatory email verification usually sends users to confirm page;
        # keep post-verify / post-login behaviour via get_login_redirect_url.
        return self.get_login_redirect_url(request)
