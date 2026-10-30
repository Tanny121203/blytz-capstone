"""Accounting chart aggregates — accepted payments only."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.orders.models import Order, Payment, PaymentChannel


def _money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(value).quantize(Decimal("0.01"))


def collected_vs_outstanding_chart(orders=None) -> dict:
    if orders is None:
        orders = list(
            Order.objects.prefetch_related("payments")
        )
    collected = sum((o.total_paid for o in orders), Decimal("0.00"))
    outstanding = sum(
        (o.balance for o in orders if o.balance is not None and o.balance > 0),
        Decimal("0.00"),
    )
    labels = ["Collected", "Outstanding"]
    values = [float(collected), float(outstanding)]
    empty = collected == 0 and outstanding == 0
    return {
        "labels": labels,
        "values": values,
        "showLegend": True,
        "empty": empty,
        "rows": [
            {"label": "Collected", "value": f"₱{collected}"},
            {"label": "Outstanding", "value": f"₱{outstanding}"},
        ],
    }


def collections_over_time_chart(days: int = 30) -> dict:
    """Sum of accepted payment amounts per day for the last `days` days."""
    now = timezone.now()
    start = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    buckets = {
        row["day"]: _money(row["total"])
        for row in (
            Payment.objects.filter(
                status=Payment.Status.ACCEPTED,
                created_at__gte=start,
            )
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Sum("amount_claimed"))
        )
        if row["day"] is not None
    }
    labels = []
    values = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        labels.append(day.strftime("%b %d"))
        amount = buckets.get(day, Decimal("0.00"))
        values.append(float(amount))
    total = sum(values)
    return {
        "labels": labels,
        "values": values,
        "datasetLabel": "Collected (₱)",
        "empty": total == 0,
        "rows": [
            {"label": labels[i], "value": f"₱{Decimal(str(values[i])).quantize(Decimal('0.01'))}"}
            for i in range(days)
            if values[i]
        ]
        or [{"label": "—", "value": "₱0.00"}],
    }


def payments_by_channel_chart() -> dict:
    """Accepted payment totals by channel kind (GCash, Maya, Bank) + Other."""
    kind_labels = {
        PaymentChannel.Kind.GCASH: "GCash",
        PaymentChannel.Kind.MAYA: "Maya",
        PaymentChannel.Kind.BANK: "Bank",
    }
    totals = {kind: Decimal("0.00") for kind in kind_labels}
    other = Decimal("0.00")

    rows = (
        Payment.objects.filter(status=Payment.Status.ACCEPTED)
        .values("channel__kind")
        .annotate(total=Sum("amount_claimed"))
    )
    for row in rows:
        kind = row["channel__kind"]
        amount = _money(row["total"])
        if kind in totals:
            totals[kind] += amount
        else:
            other += amount

    labels = [kind_labels[k] for k in kind_labels]
    values = [float(totals[k]) for k in kind_labels]
    table_rows = [
        {"label": kind_labels[k], "value": f"₱{totals[k]}"} for k in kind_labels
    ]
    if other:
        labels.append("Other")
        values.append(float(other))
        table_rows.append({"label": "Other", "value": f"₱{other}"})

    return {
        "labels": labels,
        "values": values,
        "showLegend": True,
        "empty": sum(values) == 0,
        "rows": table_rows,
    }
