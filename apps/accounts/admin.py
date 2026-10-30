from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "role",
        "phone",
        "can_edit_accounting",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = ("role", "can_edit_accounting", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Profile",
            {"fields": ("first_name", "last_name", "phone", "role", "can_edit_accounting")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "role",
                    "phone",
                    "can_edit_accounting",
                ),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")
