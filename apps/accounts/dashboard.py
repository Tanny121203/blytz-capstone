"""Staff overview dashboard aggregates (orders / pending payments)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.orders.models import Order, Payment


PHASE_LABELS = [
    (Order.Status.JOB_REQUEST, "Job Request"),
    (Order.Status.PENDING_EDIT, "Pending Edit"),
    (Order.Status.PRODUCTION, "Production"),
    (Order.Status.COMPLETED, "Completed"),
]


def orders_by_phase_chart() -> dict:
    counts = {
        row["status"]: row["c"]
        for row in Order.objects.values("status").annotate(c=Count("id"))
    }
    labels = [label for _status, label in PHASE_LABELS]
    values = [int(counts.get(status, 0)) for status, _label in PHASE_LABELS]
    total = sum(values)
    return {
        "labels": labels,
        "values": values,
        "datasetLabel": "Orders",
        "empty": total == 0,
        "rows": [
            {"label": label, "value": str(values[i])}
            for i, (_status, label) in enumerate(PHASE_LABELS)
        ],
    }


def new_orders_per_day_chart(days: int = 30) -> dict:
    now = timezone.now()
    start = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    buckets = {
        row["day"]: row["c"]
        for row in (
            Order.objects.filter(created_at__gte=start)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(c=Count("id"))
        )
        if row["day"] is not None
    }
    labels = []
    values = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        labels.append(day.strftime("%b %d"))
        values.append(int(buckets.get(day, 0)))
    total = sum(values)
    return {
        "labels": labels,
        "values": values,
        "datasetLabel": "New orders",
        "empty": total == 0,
        "rows": [
            {"label": labels[i], "value": str(values[i])}
            for i in range(days)
            if values[i]
        ]
        or [{"label": "—", "value": "0"}],
    }


def payments_awaiting_review_count() -> int:
    """Count of pending payment claims awaiting staff review."""
    return Payment.objects.filter(status=Payment.Status.PENDING).count()
