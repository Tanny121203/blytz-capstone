from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts.dashboard import (
    new_orders_per_day_chart,
    orders_by_phase_chart,
    payments_awaiting_review_count,
)
from apps.designs.models import Design
from apps.orders.models import Order
from apps.sales.models import Lead

from .decorators import admin_required, staff_required
from .forms import ProfileForm


@staff_required
def staff_home(request):
    from django.db.models import Sum, Count
    from django.utils import timezone
    from datetime import timedelta
    from apps.orders.models import Order, Payment
    
    # KPI calculations
    total_orders = Order.objects.count()
    pending_review_count = Order.objects.filter(status=Order.Status.JOB_REQUEST).count()
    in_production_count = Order.objects.filter(status=Order.Status.PRODUCTION).count()
    completed_count = Order.objects.filter(status=Order.Status.COMPLETED).count()
    
    # Total sales this month (accepted payments)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_sales = Payment.objects.filter(
        status=Payment.Status.ACCEPTED,
        created_at__gte=month_start
    ).aggregate(total=Sum('amount_claimed'))['total'] or 0
    
    # Format as Philippine peso
    total_sales_formatted = f"₱{total_sales:,.0f}"
    
    # Recent orders (last 4)
    recent_orders = Order.objects.select_related('customer', 'design').order_by('-created_at')[:4]
    
    # Recent leads (last 4)
    from apps.sales.models import Lead
    recent_leads = Lead.objects.select_related('customer', 'order__design').order_by('-created_at')[:4]
    
    # Existing chart data
    orders = Order.objects.all()
    incomplete = Design.objects.prefetch_related("orders")
    incomplete_count = sum(1 for d in incomplete if not d.is_submitted)
    phase_chart = orders_by_phase_chart()
    orders_per_day_chart = new_orders_per_day_chart(days=30)
    
    return render(
        request,
        "accounts/staff_home.html",
        {
            # KPI data
            "total_orders": total_orders,
            "pending_review_count": pending_review_count,
            "in_production_count": in_production_count,
            "completed_count": completed_count,
            "total_sales": total_sales_formatted,
            
            # Tables
            "recent_orders": recent_orders,
            "recent_leads": recent_leads,
            
            # Existing chart data (keep for Step 4)
            "stat_orders": orders.count(),
            "stat_job_requests": orders.filter(status=Order.Status.JOB_REQUEST).count(),
            "stat_leads": Lead.objects.count(),
            "stat_incomplete": incomplete_count,
            "stat_pending_review": payments_awaiting_review_count(),
            "phase_chart": phase_chart,
            "orders_per_day_chart": orders_per_day_chart,
        },
    )
@admin_required
def staff_admin_only(request):
    return render(request, "accounts/staff_admin_only.html")


@login_required
def profile(request):
    if not getattr(request.user, "is_customer", False) and not getattr(
        request.user, "is_staff_role", False
    ):
        return redirect("home")

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("account_profile")
    else:
        form = ProfileForm(instance=request.user)

    base = (
        "base_staff.html"
        if getattr(request.user, "is_staff_role", False)
        else "base_customer.html"
    )
    return render(
        request,
        "accounts/profile.html",
        {"form": form, "base_template": base},
    )
