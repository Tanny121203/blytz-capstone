from django.conf import settings
from django.db import models

from apps.designs.garment_choices import GARMENT_COLOR_CHOICES, GARMENT_TEMPLATE_CHOICES


class Design(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="designs",
    )
    title = models.CharField(max_length=200)
    # Choices aligned with static/js/editor_garments.js (see garment_choices.py).
    garment_template = models.CharField(
        max_length=100, blank=True, choices=GARMENT_TEMPLATE_CHOICES
    )
    garment_color = models.CharField(
        max_length=50, blank=True, choices=GARMENT_COLOR_CHOICES
    )
    canvas_json = models.JSONField(default=dict, blank=True)
    preview_image = models.ImageField(upload_to="design_previews/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_submitted(self) -> bool:
        """A design is submitted once it has at least one related order."""
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "orders" in cache:
            return bool(cache["orders"])
        return self.orders.exists()


class ActivityLog(models.Model):
    class Kind(models.TextChoices):
        DESIGN_CREATED = "design_created", "Design created"
        DESIGN_SUBMITTED = "design_submitted", "Design submitted"
        DESIGN_REVISED = "design_revised", "Design revised"
        DESIGN_APPROVED = "design_approved", "Design approved"
        ORDER_CONFIRMED = "order_confirmed", "Order confirmed"
        PHASE_MOVED = "phase_moved", "Phase moved"
        LEAD_STAGE_CHANGED = "lead_stage_changed", "Lead stage changed"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_logs",
    )
    design = models.ForeignKey(
        Design,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} · {self.customer}"
