from django.conf import settings
from django.db import models


class Lead(models.Model):
    class Stage(models.TextChoices):
        NEW_LEAD = "new_lead", "New Lead"
        ORDER_CONFIRMED = "order_confirmed", "Order Confirmed"
        DESIGN_REVIEW = "design_review", "Design Review"
        APPROVED = "approved", "Approved"
        COMPLETED = "completed", "Completed"
        LOST = "lost", "Lost"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leads",
    )
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="lead",
    )
    stage = models.CharField(
        max_length=32,
        choices=Stage.choices,
        default=Stage.NEW_LEAD,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.customer} · {self.get_stage_display()}"
