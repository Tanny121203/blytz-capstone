"""Validate order mock-up preview PNGs uploaded at design submit."""

from __future__ import annotations

import io
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, UnidentifiedImageError

MAX_PREVIEW_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_EDGE_PX = 2400

FRIENDLY_CORRUPT_MESSAGE = (
    "That preview does not look like a valid PNG. Please try submitting again."
)


class PreviewImageError(ValueError):
    """Raised when an uploaded preview PNG cannot be processed."""


def validate_preview_png(uploaded_file, *, field_label: str = "Preview"):
    """
    Require a real PNG under the size cap. Returns a cleaned UploadedFile.
    Raises PreviewImageError on failure.
    """
    name = getattr(uploaded_file, "name", "") or "preview.png"
    ext = Path(name).suffix.lower()
    if ext != ".png":
        raise PreviewImageError(f"{field_label} must be a PNG file.")

    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_PREVIEW_UPLOAD_BYTES:
        raise PreviewImageError(
            f"{field_label} must be 5 MB or smaller."
        )

    content_type = getattr(uploaded_file, "content_type", "") or ""
    if content_type and content_type not in {"image/png", "application/octet-stream"}:
        raise PreviewImageError(f"{field_label} must be a PNG file.")

    uploaded_file.seek(0)
    try:
        with Image.open(uploaded_file) as opened:
            opened.load()
            if opened.format != "PNG":
                raise PreviewImageError(FRIENDLY_CORRUPT_MESSAGE)
            img = opened.convert("RGBA") if opened.mode not in ("RGB", "RGBA") else opened

            w, h = img.size
            if w < 1 or h < 1:
                raise PreviewImageError(FRIENDLY_CORRUPT_MESSAGE)
            if max(w, h) > MAX_PREVIEW_EDGE_PX:
                img = img.copy()
                img.thumbnail(
                    (MAX_PREVIEW_EDGE_PX, MAX_PREVIEW_EDGE_PX),
                    Image.Resampling.LANCZOS,
                )
            else:
                img = img.copy()

            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PreviewImageError(FRIENDLY_CORRUPT_MESSAGE) from exc

    return SimpleUploadedFile(
        Path(name).name if name else "preview.png",
        buffer.getvalue(),
        content_type="image/png",
    )
