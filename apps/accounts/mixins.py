from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(AccessMixin):
    """CBV mixin: require login and a passing role check."""

    role_check = None  # callable(user) -> bool

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        check = self.role_check
        if check is None or not check(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class CustomerRequiredMixin(RoleRequiredMixin):
    role_check = staticmethod(lambda u: getattr(u, "is_customer", False))


class StaffRequiredMixin(RoleRequiredMixin):
    role_check = staticmethod(lambda u: getattr(u, "is_staff_role", False))


class AdminRequiredMixin(RoleRequiredMixin):
    role_check = staticmethod(lambda u: getattr(u, "is_admin_role", False))
