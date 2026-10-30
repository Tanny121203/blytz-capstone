"""Display helpers for the customer order / submission history list."""

from __future__ import annotations

from apps.orders.models import Order

# Page size for /app/orders/ — first pagination in this app.
ORDERS_PER_PAGE = 20


def customer_order_status_label(status: str | None) -> str:
    """
    Human-readable job phase for customers.

    Known Order.Status values use their Django labels. Anything else stays
    visible as “Unknown status (…)” and must never be shown as Completed/Paid.
    """
    known = dict(Order.Status.choices)
    if status in known:
        return known[status]
    raw = (status or "").strip()
    if raw:
        return f"Unknown status ({raw})"
    return "Unknown status"


def customer_order_status_known(status: str | None) -> bool:
    return status in dict(Order.Status.choices)
