import csv
from datetime import datetime, time
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounting.charts import (
    collections_over_time_chart,
    collected_vs_outstanding_chart,
    payments_by_channel_chart,
)
from apps.accounts.decorators import staff_required
from apps.designs.garment_choices import format_garment_display
from apps.orders.models import Order, Payment, PaymentChannel

# Read-only staff export columns. Job status ≠ payment status (Stage J/K).
ORDERS_EXPORT_HEADERS = [
    "order_id",
    "created_at",
    "customer_name",
    "customer_email",
    "design_title",
    "garment",
    "job_status",
    "payment_status",
    "agreed_total",
    "total_paid",
    "balance",
    "payment_awaiting_review",
]


def _parse_export_date(raw: str, *, end_of_day: bool = False):
    """Parse YYYY-MM-DD into an aware datetime, or None if blank. Raises ValueError if invalid."""
    value = (raw or "").strip()
    if not value:
        return None
    day = parse_date(value)
    if day is None:
        raise ValueError("invalid date")
    clock = time.max if end_of_day else time.min
    naive = datetime.combine(day, clock)
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


def _orders_export_queryset(request):
    """
    Apply validated GET filters for the staff orders CSV.

    Returns (queryset, error_response). error_response is set on bad params.
    """
    qs = Order.objects.select_related("customer", "design").prefetch_related(
        "payments"
    )

    status = (request.GET.get("status") or "").strip()
    if status:
        valid = {choice for choice, _ in Order.Status.choices}
        if status not in valid:
            return None, HttpResponse(
                "Invalid status filter. Use a job status value "
                "(job_request, pending_edit, production, completed).",
                status=400,
                content_type="text/plain; charset=utf-8",
            )
        qs = qs.filter(status=status)

    try:
        start = _parse_export_date(request.GET.get("date_from") or "")
        end = _parse_export_date(
            request.GET.get("date_to") or "", end_of_day=True
        )
    except ValueError:
        return None, HttpResponse(
            "Invalid date filter. Use YYYY-MM-DD for date_from and date_to.",
            status=400,
            content_type="text/plain; charset=utf-8",
        )
    if start and end and start > end:
        return None, HttpResponse(
            "Invalid date range. date_from must be on or before date_to.",
            status=400,
            content_type="text/plain; charset=utf-8",
        )
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)

    pending_review = (request.GET.get("pending_review") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if pending_review:
        qs = qs.filter(payments__status=Payment.Status.PENDING).distinct()

    return qs.order_by("-created_at"), None


def _format_money(value):
    if value is None:
        return ""
    return f"{Decimal(value):.2f}"


class AgreedTotalForm(forms.Form):
    agreed_total = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=True,
    )


class ManualPaymentForm(forms.Form):
    amount_claimed = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    note = forms.CharField(max_length=255, required=False)
    channel = forms.ModelChoiceField(
        queryset=PaymentChannel.objects.filter(is_active=True),
        required=False,
    )
    proof_file = forms.FileField(required=False)

    def clean_amount_claimed(self):
        amount = self.cleaned_data["amount_claimed"]
        if amount == 0:
            raise forms.ValidationError("Amount cannot be zero.")
        return amount


@staff_required
def accounting_list(request):
    orders = list(
        Order.objects.select_related("customer", "design").prefetch_related("payments")
    )
    total_collected = sum((o.total_paid for o in orders), Decimal("0.00"))
    total_outstanding = sum(
        (o.balance for o in orders if o.balance is not None and o.balance > 0),
        Decimal("0.00"),
    )
    collected_chart = collected_vs_outstanding_chart(orders)
    collections_chart = collections_over_time_chart(days=30)
    channel_chart = payments_by_channel_chart()
    return render(
        request,
        "accounting/list.html",
        {
            "orders": orders,
            "total_collected": total_collected,
            "total_outstanding": total_outstanding,
            "can_edit": request.user.can_edit_accounting_page(),
            "collected_chart": collected_chart,
            "collections_chart": collections_chart,
            "channel_chart": channel_chart,
            "export_status_choices": Order.Status.choices,
        },
    )


@staff_required
@require_GET
def accounting_export_csv(request):
    """
    Staff/admin read-only CSV of orders for reporting.

    Does not mutate Order, Payment, or Design records. Job status and payment
    status are separate columns (aligned with staff UI labels).
    """
    qs, err = _orders_export_queryset(request)
    if err is not None:
        return err

    job_labels = dict(Order.Status.choices)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="blytz-orders-export.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(ORDERS_EXPORT_HEADERS)

    for order in qs:
        design = order.design
        customer = order.customer
        writer.writerow(
            [
                order.order_id,
                timezone.localtime(order.created_at).strftime("%Y-%m-%d %H:%M"),
                customer.get_full_name() if customer else "",
                customer.email if customer else "",
                design.title if design else "",
                format_garment_display(
                    design.garment_template if design else "",
                    design.garment_color if design else "",
                ),
                job_labels.get(order.status, order.status),
                order.payment_status,
                _format_money(order.agreed_total),
                _format_money(order.total_paid),
                _format_money(order.balance),
                "yes" if order.pending_payment else "no",
            ]
        )
    return response


@staff_required
@require_http_methods(["GET", "POST"])
def accounting_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related(
            "customer", "design", "accounting_edited_by"
        ).prefetch_related("payments__channel", "payments__recorded_by"),
        order_id=order_id,
    )
    can_edit = request.user.can_edit_accounting_page()
    total_form = AgreedTotalForm(initial={"agreed_total": order.agreed_total})
    payment_form = ManualPaymentForm()

    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied

        action = request.POST.get("action")
        if action == "set_total":
            total_form = AgreedTotalForm(request.POST)
            if total_form.is_valid():
                order.agreed_total = total_form.cleaned_data["agreed_total"]
                order.accounting_edited_by = request.user
                order.accounting_edited_at = timezone.now()
                order.save(
                    update_fields=[
                        "agreed_total",
                        "accounting_edited_by",
                        "accounting_edited_at",
                    ]
                )
                messages.success(request, "Agreed total updated.")
                return redirect("accounting_detail", order_id=order.order_id)
        elif action == "add_payment":
            payment_form = ManualPaymentForm(request.POST, request.FILES)
            if payment_form.is_valid():
                now = timezone.now()
                Payment.objects.create(
                    order=order,
                    channel=payment_form.cleaned_data.get("channel"),
                    amount_claimed=payment_form.cleaned_data["amount_claimed"],
                    proof_file=payment_form.cleaned_data.get("proof_file"),
                    is_manual_adjustment=True,
                    note=payment_form.cleaned_data.get("note") or "Manual adjustment",
                    recorded_by=request.user,
                    status=Payment.Status.ACCEPTED,
                    reviewed_by=request.user,
                    reviewed_at=now,
                )
                order.accounting_edited_by = request.user
                order.accounting_edited_at = timezone.now()
                order.save(
                    update_fields=["accounting_edited_by", "accounting_edited_at"]
                )
                messages.success(request, "Manual payment recorded.")
                return redirect("accounting_detail", order_id=order.order_id)
        else:
            raise PermissionDenied

    return render(
        request,
        "accounting/detail.html",
        {
            "order": order,
            "payments": order.payments.all(),
            "can_edit": can_edit,
            "total_form": total_form,
            "payment_form": payment_form,
        },
    )
