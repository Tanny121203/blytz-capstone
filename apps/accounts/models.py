from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        STAFF = "staff", "Staff"
        ADMIN = "admin", "Admin"

    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    can_edit_accounting = models.BooleanField(
        default=False,
        help_text="Only meaningful for staff. Admins always can edit accounting.",
    )

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER

    @property
    def is_staff_role(self) -> bool:
        return self.role in {self.Role.STAFF, self.Role.ADMIN}

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN

    def can_edit_accounting_page(self) -> bool:
        """Admins always can; staff only when the flag is granted."""
        if self.is_admin_role:
            return True
        if self.role == self.Role.STAFF and self.can_edit_accounting:
            return True
        return False

    def get_full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]
