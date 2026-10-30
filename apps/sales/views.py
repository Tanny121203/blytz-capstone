from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import staff_required
from apps.designs.models import ActivityLog, Design

from .models import Lead


@staff_required
def sales_pipeline(request):
    tab = request.GET.get("tab", "leads")
    leads = Lead.objects.select_related("customer", "order", "order__design").order_by(
        "-created_at"
    )

    stages = []
    for value, label in Lead.Stage.choices:
        stages.append(
            {
                "value": value,
                "label": label,
                "leads": [lead for lead in leads if lead.stage == value],
            }
        )

    incomplete = []
    if tab == "incomplete":
        incomplete = (
            Design.objects.select_related("owner")
            .prefetch_related("orders")
            .order_by("-updated_at")
        )
        incomplete = [d for d in incomplete if not d.is_submitted]

    return render(
        request,
        "sales/pipeline.html",
        {
            "stages": stages,
            "stage_choices": Lead.Stage.choices,
            "tab": tab,
            "incomplete_designs": incomplete,
        },
    )


@staff_required
@require_POST
def update_lead_stage(request, lead_id):
    lead = get_object_or_404(Lead.objects.select_related("customer", "order"), pk=lead_id)
    new_stage = request.POST.get("stage")
    valid = {c[0] for c in Lead.Stage.choices}
    if new_stage not in valid:
        messages.error(request, "Invalid stage.")
        return redirect("sales_pipeline")

    if lead.stage != new_stage:
        lead.stage = new_stage
        lead.save(update_fields=["stage"])
        ActivityLog.objects.create(
            customer=lead.customer,
            design=lead.order.design if lead.order_id else None,
            order=lead.order,
            kind=ActivityLog.Kind.LEAD_STAGE_CHANGED,
        )
        messages.success(request, f"Lead moved to {lead.get_stage_display()}.")
    return redirect(request.POST.get("next") or "sales_pipeline")


@staff_required
def lead_detail(request, lead_id):
    lead = get_object_or_404(
        Lead.objects.select_related("customer", "order", "order__design"),
        pk=lead_id,
    )
    timeline = ActivityLog.objects.filter(customer=lead.customer).select_related(
        "design", "order"
    )
    return render(
        request,
        "sales/lead_detail.html",
        {
            "lead": lead,
            "timeline": timeline,
            "stage_choices": Lead.Stage.choices,
        },
    )
