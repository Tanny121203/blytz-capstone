"""Shared payment-proof and final-design file validation."""

from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings
from PIL import Image, UnidentifiedImageError

from services.proof_images import ProofImageError, process_proof_file

ALLOWED_PROOF_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
ALLOWED_PROOF_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "application/pdf",
}

FRIENDLY_FINAL_CORRUPT = (
    "That file does not look like a valid image. "
    "Please upload a real PNG or JPG, or a PDF."
)


def proof_max_bytes() -> int:
    return int(settings.PROOF_MAX_UPLOAD_MB) * 1024 * 1024


def proof_max_label() -> str:
    return f"{int(settings.PROOF_MAX_UPLOAD_MB)} MB"


def _validate_allowed_upload(uploaded, *, label: str):
    """Shared extension / size / content-type checks. Returns lowercase ext."""
    name = (getattr(uploaded, "name", "") or "").lower()
    ext = Path(name).suffix
    if ext not in ALLOWED_PROOF_EXTENSIONS:
        raise forms.ValidationError(
            f"{label} must be a PNG, JPG, JPEG, or PDF file."
        )
    max_bytes = proof_max_bytes()
    if uploaded.size > max_bytes:
        raise forms.ValidationError(
            f"{label} must be {proof_max_label()} or smaller."
        )
    content_type = getattr(uploaded, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_PROOF_CONTENT_TYPES:
        if content_type not in {"application/octet-stream", ""}:
            raise forms.ValidationError(
                f"{label} must be a PNG, JPG, JPEG, or PDF file."
            )
    return ext


def validate_and_process_proof(proof):
    """
    Validate extension/size/type, then shrink/sanitize images (PDFs untouched).
    Returns the (possibly replaced) uploaded file.
    """
    _validate_allowed_upload(proof, label="Proof")
    try:
        return process_proof_file(proof)
    except ProofImageError as exc:
        raise forms.ValidationError(str(exc)) from exc


def validate_final_design_file(uploaded):
    """
    Validate extension/size/type for final designs.
    Does not shrink, re-encode, or alter the file.
    """
    ext = _validate_allowed_upload(uploaded, label="Final design")
    if ext == ".pdf":
        uploaded.seek(0)
        return uploaded
    uploaded.seek(0)
    try:
        with Image.open(uploaded) as img:
            img.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise forms.ValidationError(FRIENDLY_FINAL_CORRUPT) from exc
    uploaded.seek(0)
    return uploaded
