from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _user_passes(test_func):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not test_func(request.user):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def customer_required(view_func):
    """Allow only users with the customer role."""
    return _user_passes(lambda u: getattr(u, "is_customer", False))(view_func)


def staff_required(view_func):
    """Allow staff and admin roles."""
    return _user_passes(lambda u: getattr(u, "is_staff_role", False))(view_func)


def admin_required(view_func):
    """Allow only the admin role."""
    return _user_passes(lambda u: getattr(u, "is_admin_role", False))(view_func)
