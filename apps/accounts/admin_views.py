from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required

User = get_user_model()


class StaffCreateForm(forms.Form):
    email = forms.EmailField()
    temporary_password = forms.CharField(min_length=8)
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    can_edit_accounting = forms.BooleanField(required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with that email already exists.")
        return email


class UserRoleForm(forms.Form):
    role = forms.ChoiceField(choices=User.Role.choices)
    can_edit_accounting = forms.BooleanField(required=False)
    is_active = forms.BooleanField(required=False)


def _active_admin_count():
    return User.objects.filter(role=User.Role.ADMIN, is_active=True).count()


@admin_required
def user_manage_list(request):
    users = User.objects.all().order_by("role", "email")
    return render(
        request,
        "accounts/users_list.html",
        {"users": users, "empty": not users.exists()},
    )


@admin_required
def user_create_staff(request):
    form = StaffCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["temporary_password"],
            role=User.Role.STAFF,
            is_staff=True,
            first_name=form.cleaned_data.get("first_name") or "",
            last_name=form.cleaned_data.get("last_name") or "",
            can_edit_accounting=bool(form.cleaned_data.get("can_edit_accounting")),
        )
        messages.success(request, f"Staff account created for {user.email}.")
        return redirect("user_manage_list")
    return render(
        request,
        "accounts/user_create.html",
        {"form": form},
    )


@admin_required
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    initial = {
        "role": target.role,
        "can_edit_accounting": target.can_edit_accounting,
        "is_active": target.is_active,
    }
    form = UserRoleForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        new_role = form.cleaned_data["role"]
        new_active = form.cleaned_data["is_active"]
        new_acct = form.cleaned_data["can_edit_accounting"]

        # Guard: cannot demote or deactivate self
        if target.pk == request.user.pk:
            if new_role != User.Role.ADMIN:
                form.add_error("role", "You cannot demote yourself.")
            if not new_active:
                form.add_error("is_active", "You cannot deactivate yourself.")

        # Guard: always keep at least one active admin
        if not form.errors:
            would_lose_admin = (
                target.role == User.Role.ADMIN
                and target.is_active
                and (new_role != User.Role.ADMIN or not new_active)
            )
            if would_lose_admin and _active_admin_count() <= 1:
                form.add_error(
                    None,
                    "The system must keep at least one active admin.",
                )

        if not form.errors:
            target.role = new_role
            target.is_active = new_active
            target.is_staff = new_role in {User.Role.STAFF, User.Role.ADMIN}
            target.is_superuser = new_role == User.Role.ADMIN
            if new_role == User.Role.STAFF:
                target.can_edit_accounting = new_acct
            elif new_role == User.Role.ADMIN:
                target.can_edit_accounting = False  # admins use can_edit_accounting_page()
            else:
                target.can_edit_accounting = False
            target.save()
            messages.success(request, f"Updated {target.email}.")
            return redirect("user_manage_list")

    return render(
        request,
        "accounts/user_edit.html",
        {"form": form, "target": target},
    )
