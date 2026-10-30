import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import customer_required
from apps.orders.models import Order, Payment, PaymentChannel
from apps.sales.models import Lead
from services.ai_design import AIDesignError, gemini_configured, suggest_design_candidates

from .ai_suggest import (
    AI_BOUNDS_MAX_RETRIES,
    AISuggestValidationError,
    check_rate_limit,
    record_rate_limit_success,
    should_generate_dual_side,
    validate_two_candidates,
)
from .forms import DesignSaveForm, DesignSubmitForm
from .garment_choices import normalize_garment_template
from .models import ActivityLog, Design
from .print_areas_catalog import get_print_areas, primary_print_areas

logger = logging.getLogger(__name__)


def _wants_json(request) -> bool:
    accept = request.headers.get("Accept", "")
    return (
        "application/json" in accept
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


@customer_required
def dashboard(request):
    designs = Design.objects.filter(owner=request.user).order_by("-updated_at")
    orders = Order.objects.filter(customer=request.user).select_related("design")

    designs_list = list(designs)
    submitted_ids = set(
        Order.objects.filter(design_id__in=[d.pk for d in designs_list]).values_list(
            "design_id", flat=True
        )
    )
    submitted_count = len(submitted_ids)
    draft_count = len(designs_list) - submitted_count

    return render(
        request,
        "designs/dashboard.html",
        {
            "designs": designs_list[:5],
            "orders": orders[:5],
            "stat_designs": len(designs_list),
            "stat_drafts": draft_count,
            "stat_submitted": submitted_count,
            "stat_orders": orders.count(),
            "submitted_ids": submitted_ids,
        },
    )


@customer_required
def design_list(request):
    designs = Design.objects.filter(owner=request.user).prefetch_related("orders")
    return render(request, "designs/design_list.html", {"designs": designs})


@customer_required
def design_detail(request, pk):
    design = get_object_or_404(Design, pk=pk, owner=request.user)
    return redirect("design_editor", pk=design.pk)


@customer_required
def design_create(request):
    if request.method != "POST":
        return redirect("design_list")

    design = Design.objects.create(
        owner=request.user,
        title="Untitled design",
        garment_template="tee",
        garment_color="black",
        canvas_json={"version": 1, "objects": []},
    )
    ActivityLog.objects.create(
        customer=request.user,
        design=design,
        kind=ActivityLog.Kind.DESIGN_CREATED,
    )
    messages.success(request, "Draft design created.")
    return redirect("design_editor", pk=design.pk)


@customer_required
def design_editor(request, pk):
    design = get_object_or_404(Design, pk=pk, owner=request.user)
    channels = PaymentChannel.objects.filter(is_active=True)
    return render(
        request,
        "designs/editor.html",
        {
            "design": design,
            "channels": channels,
            "payment_window_minutes": settings.PAYMENT_WINDOW_MINUTES,
            "already_submitted": design.is_submitted,
            "canvas_json_initial": json.dumps(design.canvas_json or {}),
            "ai_suggest_enabled": gemini_configured(),
        },
    )


@customer_required
@require_POST
def design_save(request, pk):
    design = get_object_or_404(Design, pk=pk, owner=request.user)
    if design.is_submitted:
        msg = "This design already has an order and can no longer be saved or renamed."
        if _wants_json(request):
            return JsonResponse({"ok": False, "errors": {"design": [msg]}}, status=400)
        messages.error(request, msg)
        return redirect("design_editor", pk=pk)

    form = DesignSaveForm(request.POST, stored_canvas=design.canvas_json)
    if not form.is_valid():
        if _wants_json(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Could not save design.")
        return redirect("design_editor", pk=pk)

    design.canvas_json = form.cleaned_data["canvas_json"]
    if "title" in request.POST:
        design.title = form.cleaned_data["title"]
    if form.cleaned_data.get("garment_template") is not None:
        design.garment_template = form.cleaned_data["garment_template"]
    if form.cleaned_data.get("garment_color") is not None:
        design.garment_color = form.cleaned_data["garment_color"]
    design.save()

    if _wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "updated_at": design.updated_at.isoformat(),
                "title": design.title,
            }
        )
    messages.success(request, "Design saved.")
    return redirect("design_editor", pk=pk)


def _submit_already_response(request, pk):
    """AJAX clients need JSON; HTML keeps redirect + message."""
    msg = "This design was already submitted."
    if _wants_json(request):
        return JsonResponse({"ok": False, "errors": {"design": [msg]}}, status=400)
    messages.error(request, msg)
    return redirect("design_editor", pk=pk)


def _database_lock_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "locked" in text
        or "lock wait timeout" in text
        or "deadlock" in text
    )


def _submit_conflict_response(request, pk):
    """
    Lost a concurrent insert (unique design, or the writer lock).
    Never include database exception text in the response.
    """
    if Order.objects.filter(design_id=pk).exists():
        return _submit_already_response(request, pk)
    msg = "Could not submit this design. Please try again."
    if _wants_json(request):
        return JsonResponse({"ok": False, "errors": {"design": [msg]}}, status=400)
    messages.error(request, msg)
    return redirect("design_editor", pk=pk)


@customer_required
@require_POST
def design_submit(request, pk):
    design = get_object_or_404(Design, pk=pk, owner=request.user)

    if design.is_submitted:
        return _submit_already_response(request, pk)

    form = DesignSubmitForm(
        request.POST, request.FILES, stored_canvas=design.canvas_json
    )
    if not form.is_valid():
        if _wants_json(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        for err in form.errors.values():
            messages.error(request, err.as_text())
        return redirect("design_editor", pk=pk)

    started = form.cleaned_data["window_started_at"]
    deadline = started + timedelta(minutes=settings.PAYMENT_WINDOW_MINUTES)
    if timezone.now() > deadline:
        if _wants_json(request):
            return JsonResponse(
                {"ok": False, "errors": {"window": ["Payment window expired."]}},
                status=400,
            )
        messages.error(request, "Payment window expired. Nothing was recorded.")
        return redirect("design_editor", pk=pk)

    channel = form.cleaned_data["channel"]
    amount = form.cleaned_data["amount_claimed"]
    proof = form.cleaned_data["proof_file"]
    canvas = form.cleaned_data["canvas_json"]
    preview_front = form.cleaned_data["preview_image"]
    preview_back = form.cleaned_data["preview_back_image"]

    # One retry: SQLite can return "database is locked" immediately when two
    # deferred transactions both already hold a read lock. After this request
    # rolls back, the other writer can commit and the retry observes it.
    order = None
    for attempt in range(2):
        try:
            with transaction.atomic():
                # Write the design row before the re-check. select_for_update()
                # locks that row on MySQL/PostgreSQL, but Django's SQLite
                # backend does not emit FOR UPDATE. The UPDATE reserves
                # SQLite's writer lock so a second submit waits, then sees
                # this order. unique_order_per_design is the constraint backstop.
                locked = Design.objects.filter(pk=pk, owner=request.user).update(
                    updated_at=timezone.now()
                )
                if locked != 1:
                    raise Http404()
                design = Design.objects.select_for_update().get(
                    pk=pk, owner=request.user
                )
                if design.is_submitted:
                    transaction.set_rollback(True)
                    order = None
                else:
                    design.canvas_json = canvas
                    update_fields = ["canvas_json", "updated_at"]
                    if form.cleaned_data.get("garment_template") is not None:
                        design.garment_template = form.cleaned_data["garment_template"]
                        update_fields.append("garment_template")
                    if form.cleaned_data.get("garment_color") is not None:
                        design.garment_color = form.cleaned_data["garment_color"]
                        update_fields.append("garment_color")
                    design.save(update_fields=update_fields)

                    # Staff read garment on order.design; both views live in
                    # order.canvas_json_snapshot (and design.canvas_json) under B1.
                    # Front/back mock-up PNGs (garment + artwork) are required.
                    order = Order.objects.create(
                        customer=request.user,
                        design=design,
                        canvas_json_snapshot=canvas,
                        preview_image=preview_front,
                        preview_back_image=preview_back,
                        status=Order.Status.JOB_REQUEST,
                        notes="Submitted from editor with payment claim.",
                    )
                    Payment.objects.create(
                        order=order,
                        channel=channel,
                        amount_claimed=amount,
                        proof_file=proof,
                    )
                    Lead.objects.create(
                        customer=request.user,
                        order=order,
                        stage=Lead.Stage.NEW_LEAD,
                    )
                    ActivityLog.objects.create(
                        customer=request.user,
                        design=design,
                        order=order,
                        kind=ActivityLog.Kind.DESIGN_SUBMITTED,
                    )
                    ActivityLog.objects.create(
                        customer=request.user,
                        design=design,
                        order=order,
                        kind=ActivityLog.Kind.ORDER_CONFIRMED,
                    )
            break
        except ValidationError as exc:
            if _wants_json(request):
                return JsonResponse(
                    {"ok": False, "errors": {"design": [str(exc)]}}, status=400
                )
            messages.error(request, str(exc))
            return redirect("design_editor", pk=pk)
        except IntegrityError:
            if attempt == 0:
                for uploaded in (proof, preview_front, preview_back):
                    if hasattr(uploaded, "seek"):
                        uploaded.seek(0)
                continue
            return _submit_conflict_response(request, pk)
        except OperationalError as exc:
            if _database_lock_error(exc) and attempt == 0:
                for uploaded in (proof, preview_front, preview_back):
                    if hasattr(uploaded, "seek"):
                        uploaded.seek(0)
                continue
            if _database_lock_error(exc):
                return _submit_conflict_response(request, pk)
            raise

    if order is None:
        return _submit_already_response(request, pk)

    messages.success(request, f"Order {order.order_id} created.")
    if _wants_json(request):
        return JsonResponse({"ok": True, "redirect": order.get_absolute_url()})
    return redirect("order_detail", order_id=order.order_id)


def _parse_ai_suggest_body(request):
    """Parse JSON or form-encoded AI suggest body. Never logs canvas content."""
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "Invalid JSON body."
        if not isinstance(payload, dict):
            return None, "Request body must be a JSON object."
    else:
        payload = {
            "message": request.POST.get("message", ""),
            "canvas_json": request.POST.get("canvas_json"),
            "active_side": request.POST.get("active_side", "front"),
            "garment_template": request.POST.get("garment_template", ""),
            "garment_color": request.POST.get("garment_color", ""),
        }
        raw_canvas = payload.get("canvas_json")
        if isinstance(raw_canvas, str) and raw_canvas.strip():
            try:
                payload["canvas_json"] = json.loads(raw_canvas)
            except json.JSONDecodeError:
                return None, "Invalid canvas_json."

    message = str(payload.get("message") or "").strip()
    if not message:
        return None, "Enter a design prompt."
    if len(message) > 2000:
        return None, "Prompt is too long (max 2000 characters)."

    active_side = str(payload.get("active_side") or "front").strip().lower()
    if active_side not in ("front", "back"):
        return None, "active_side must be front or back."

    canvas = payload.get("canvas_json")
    if canvas is None:
        canvas = payload.get("canvas")
    if canvas is None:
        canvas = {}
    if isinstance(canvas, str):
        try:
            canvas = json.loads(canvas) if canvas.strip() else {}
        except json.JSONDecodeError:
            return None, "Invalid canvas_json."
    if not isinstance(canvas, dict):
        return None, "canvas_json must be an object."

    return {
        "message": message,
        "canvas_json": canvas,
        "active_side": active_side,
        # Client hints ignored when Design row has values (see view).
        "garment_template_hint": str(payload.get("garment_template") or "").strip(),
        "garment_color_hint": str(payload.get("garment_color") or "").strip(),
    }, None


@customer_required
@require_POST
def design_ai_suggest(request, pk):
    """
    Stage O / O.1: two AI design candidates via Gemini.

    Zone-aware prompts, print-bounds validation (+ retries), image merge,
    optional jersey/dual-side otherSideCanvasJSON.

    Never mutates Design.canvas_json or creates Orders. Customer-owned designs only.
    """
    design = get_object_or_404(Design, pk=pk, owner=request.user)

    if not gemini_configured():
        logger.info(
            "ai_suggest unavailable user_id=%s design_id=%s",
            request.user.pk,
            pk,
        )
        return JsonResponse(
            {
                "ok": False,
                "error": "AI suggestions are unavailable right now.",
                "code": "ai_unavailable",
            },
            status=503,
        )

    allowed, _remaining = check_rate_limit(request.user.pk)
    if not allowed:
        logger.info(
            "ai_suggest rate_limited user_id=%s design_id=%s",
            request.user.pk,
            pk,
        )
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "You have reached the AI suggestion limit "
                    f"({settings.AI_SUGGEST_RATE_LIMIT_PER_HOUR} per hour). "
                    "Try again later, or keep editing manually."
                ),
                "code": "rate_limited",
            },
            status=429,
        )

    parsed, err = _parse_ai_suggest_body(request)
    if err:
        return JsonResponse({"ok": False, "error": err, "code": "bad_request"}, status=400)

    garment = normalize_garment_template(design.garment_template) or "tee"
    color = (design.garment_color or "").strip().lower() or "white"
    active_side = parsed["active_side"]
    other_side = "back" if active_side == "front" else "front"
    dual_side = should_generate_dual_side(garment, parsed["message"])
    print_areas = primary_print_areas(get_print_areas(garment, active_side))
    other_areas = (
        primary_print_areas(get_print_areas(garment, other_side))
        if dual_side
        else []
    )

    result = None
    suggestions = None
    last_validation_error = None
    attempts = 1 + AI_BOUNDS_MAX_RETRIES
    repair_hint = None

    for attempt in range(attempts):
        try:
            result = suggest_design_candidates(
                message=parsed["message"],
                canvas_json=parsed["canvas_json"],
                active_side=active_side,
                garment_template=garment,
                garment_color=color,
                print_areas=print_areas,
                other_side_print_areas=other_areas,
                dual_side=dual_side,
                repair_hint=repair_hint,
            )
            suggestions = validate_two_candidates(
                result["suggestions"],
                garment_template=garment,
                active_side=active_side,
                prior_canvas=parsed["canvas_json"],
                message=parsed["message"],
                dual_side=dual_side,
            )
            last_validation_error = None
            break
        except AIDesignError as exc:
            logger.info(
                "ai_suggest failure user_id=%s design_id=%s code=%s attempt=%s",
                request.user.pk,
                pk,
                exc.code,
                attempt + 1,
            )
            status = 503 if exc.code == "ai_unavailable" else 400
            return JsonResponse(
                {"ok": False, "error": exc.message, "code": exc.code},
                status=status,
            )
        except AISuggestValidationError as exc:
            last_validation_error = exc
            repair_hint = (
                f"{exc.message} Prefer the printable panel; only a small overflow "
                "is allowed. Retry with corrected left/top/width/height closer "
                "to the panel."
            )
            logger.info(
                "ai_suggest invalid_candidates user_id=%s design_id=%s attempt=%s",
                request.user.pk,
                pk,
                attempt + 1,
            )

    if last_validation_error is not None or suggestions is None:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    last_validation_error.message
                    if last_validation_error
                    else "AI candidates failed validation."
                ),
                "code": "invalid_candidates",
            },
            status=400,
        )

    record_rate_limit_success(request.user.pk)
    usage = (result or {}).get("usage") or {}
    logger.info(
        "ai_suggest success user_id=%s design_id=%s prompt_tokens=%s "
        "output_tokens=%s dual_side=%s",
        request.user.pk,
        pk,
        usage.get("prompt_tokens"),
        usage.get("output_tokens"),
        dual_side,
    )

    return JsonResponse(
        {
            "ok": True,
            "message": (result or {}).get("message")
            or "Here are two design candidates. Select one to preview.",
            "suggestions": suggestions,
            "active_side": active_side,
            "dual_side": dual_side,
            "garment_template": garment,
            "print_areas": print_areas,
        }
    )