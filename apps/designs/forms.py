import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.designs.canvas_safety import CanvasSafetyError, validate_v1_envelope
from apps.designs.garment_choices import (
    GARMENT_COLOR_IDS,
    GARMENT_TEMPLATE_IDS,
    apply_stale_client_views_guard,
)
from apps.orders.models import PaymentChannel
from apps.orders.proof import validate_and_process_proof
from services.preview_images import PreviewImageError, validate_preview_png

# Match client MAX_CANVAS_JSON_BYTES (2 MiB UTF-8).
MAX_CANVAS_JSON_BYTES = 2 * 1024 * 1024


def _utf8_byte_length(value: str) -> int:
    return len(value.encode("utf-8"))


def _apply_v1_safety(data: dict) -> dict:
    """
    Run shared safety scan only for schema_version == 1.
    Non-v1 payloads stay opaque (must stay identical to client policy).
    Rules: apps/designs/canvas_safety.py ↔ static/js/editor_canvas.js scanCanvasPayload.
    """
    if isinstance(data, dict) and data.get("schema_version") == 1:
        try:
            validate_v1_envelope(data)
        except CanvasSafetyError as exc:
            raise forms.ValidationError(
                "This design contains content that cannot be saved safely."
            ) from exc
    return data


def _is_unsupported_legacy(data: dict) -> bool:
    """
    Match client isUnsupportedLegacy in editor_canvas.js.

    Genuinely supported (not rejected here):
      - Blytz schema_version 1 envelopes
      - Empty legacy stubs: {version: 1, objects: []}
      - Raw Fabric canvases: {version: "<string>", objects: [...]}
      - Unknown schema_version ≠ 1 (opaque forward-compat; client blocks UI overwrite)

    Unsupported (reject on save/submit — editor cannot load these):
      - Non-empty pre-Fabric stubs, e.g. {version: 1, objects: [{type: "text"}]}
    """
    if not isinstance(data, dict):
        return False
    if "schema_version" in data:
        return False
    version = data.get("version")
    objects = data.get("objects")
    # Raw Fabric: version is a string + objects array (client wraps into v1 on load).
    if isinstance(version, str) and isinstance(objects, list):
        return False
    return isinstance(objects, list) and len(objects) > 0


def _parse_canvas_json(raw, *, stored_canvas=None):
    if isinstance(raw, dict):
        data = raw
    elif not raw:
        data = {}
    elif not isinstance(raw, str):
        raise forms.ValidationError("Invalid canvas JSON.")
    else:
        if _utf8_byte_length(raw) > MAX_CANVAS_JSON_BYTES:
            raise forms.ValidationError("Canvas JSON exceeds the 2 MiB size limit.")
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise forms.ValidationError("Invalid canvas JSON.") from exc
        if not isinstance(data, dict):
            raise forms.ValidationError("Canvas JSON must be an object.")

    # Stale-client guard before size re-encode / safety (v1 only; non-v1 opaque).
    data = apply_stale_client_views_guard(data, stored_canvas)

    # Align with editor load rules: do not persist formats the client cannot open.
    # Do not broaden acceptance — only reject what the editor already blocks.
    if _is_unsupported_legacy(data):
        raise forms.ValidationError(
            "This design uses an unsupported legacy canvas format."
        )

    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if _utf8_byte_length(encoded) > MAX_CANVAS_JSON_BYTES:
        raise forms.ValidationError(
            "Canvas JSON exceeds the 2 MiB size limit."
        )
    return _apply_v1_safety(data)


def _clean_optional_garment_template(value):
    if value in (None, ""):
        return None
    if value not in GARMENT_TEMPLATE_IDS:
        raise forms.ValidationError("Invalid garment selection.")
    return value


def _clean_optional_garment_color(value):
    if value in (None, ""):
        return None
    if value not in GARMENT_COLOR_IDS:
        raise forms.ValidationError("Invalid garment selection.")
    return value


class DesignSaveForm(forms.Form):
    canvas_json = forms.CharField(required=False)
    title = forms.CharField(max_length=200, required=False)
    # Optional; absent means unchanged. Cross-ref: garment_choices.py ↔ editor_garments.js
    garment_template = forms.CharField(max_length=100, required=False)
    garment_color = forms.CharField(max_length=50, required=False)

    def __init__(self, *args, stored_canvas=None, **kwargs):
        self.stored_canvas = stored_canvas
        super().__init__(*args, **kwargs)

    def clean_canvas_json(self):
        return _parse_canvas_json(
            self.cleaned_data.get("canvas_json") or "{}",
            stored_canvas=self.stored_canvas,
        )

    def clean_title(self):
        # Only normalize when the client actually sent title (see design_save).
        if self.data is not None and "title" not in self.data:
            return None
        raw = self.cleaned_data.get("title") or ""
        title = raw.strip()
        if not title:
            return "Untitled design"
        return title[:200]

    def clean_garment_template(self):
        return _clean_optional_garment_template(
            self.cleaned_data.get("garment_template")
        )

    def clean_garment_color(self):
        return _clean_optional_garment_color(self.cleaned_data.get("garment_color"))


class DesignSubmitForm(forms.Form):
    channel = forms.ModelChoiceField(
        queryset=PaymentChannel.objects.filter(is_active=True),
    )
    amount_claimed = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    proof_file = forms.FileField()
    preview_image = forms.FileField()
    preview_back_image = forms.FileField()
    canvas_json = forms.CharField(required=False)
    window_started_at = forms.CharField()
    garment_template = forms.CharField(max_length=100, required=False)
    garment_color = forms.CharField(max_length=50, required=False)

    def __init__(self, *args, stored_canvas=None, **kwargs):
        self.stored_canvas = stored_canvas
        super().__init__(*args, **kwargs)

    def clean_canvas_json(self):
        return _parse_canvas_json(
            self.cleaned_data.get("canvas_json") or "{}",
            stored_canvas=self.stored_canvas,
        )

    def clean_garment_template(self):
        return _clean_optional_garment_template(
            self.cleaned_data.get("garment_template")
        )

    def clean_garment_color(self):
        return _clean_optional_garment_color(self.cleaned_data.get("garment_color"))

    def clean_window_started_at(self):
        raw = self.cleaned_data["window_started_at"]
        started = parse_datetime(raw)
        if started is None:
            raise forms.ValidationError("Invalid payment window timestamp.")
        if timezone.is_naive(started):
            started = timezone.make_aware(started, timezone.get_current_timezone())
        # Reject absurd future starts
        if started > timezone.now() + timedelta(minutes=1):
            raise forms.ValidationError("Invalid payment window start.")
        return started

    def clean_proof_file(self):
        return validate_and_process_proof(self.cleaned_data["proof_file"])

    def clean_preview_image(self):
        try:
            return validate_preview_png(
                self.cleaned_data["preview_image"],
                field_label="Front preview",
            )
        except PreviewImageError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_preview_back_image(self):
        try:
            return validate_preview_png(
                self.cleaned_data["preview_back_image"],
                field_label="Back preview",
            )
        except PreviewImageError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_amount_claimed(self):
        amount = self.cleaned_data["amount_claimed"]
        try:
            amount = Decimal(amount)
        except (InvalidOperation, TypeError) as exc:
            raise forms.ValidationError("Enter a valid amount.") from exc
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount
