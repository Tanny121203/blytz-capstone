"""Shrink and sanitize payment-proof images (PNG/JPEG). PDFs pass through."""

from __future__ import annotations

import io
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

PROOF_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_PROOF_EDGE_PX = 2000
JPEG_QUALITY = 85

FRIENDLY_CORRUPT_MESSAGE = (
    "That proof file does not look like a valid image. "
    "Please upload a real PNG or JPG, or a PDF."
)


class ProofImageError(ValueError):
    """Raised when an uploaded proof image cannot be processed."""


def _extension(name: str) -> str:
    return Path(name or "").suffix.lower()


def _strip_metadata(img: Image.Image) -> Image.Image:
    """Return a pixel-identical copy with no EXIF/XMP/info payload."""
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    return clean


def process_proof_file(uploaded_file):
    """
    Validate/shrink image proofs; leave PDFs unchanged.

    Returns a new UploadedFile-like object ready to assign to FileField.
    Raises ProofImageError for corrupt or fake images.
    """
    name = getattr(uploaded_file, "name", "") or "proof"
    ext = _extension(name)

    if ext == ".pdf":
        uploaded_file.seek(0)
        return uploaded_file

    if ext not in PROOF_IMAGE_EXTENSIONS:
        return uploaded_file

    uploaded_file.seek(0)
    try:
        with Image.open(uploaded_file) as opened:
            opened.load()
            # Apply EXIF orientation before stripping metadata (incl. GPS).
            img = ImageOps.exif_transpose(opened)
            if img is None:
                raise ProofImageError(FRIENDLY_CORRUPT_MESSAGE)

            if ext == ".png":
                if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    img = img.convert("RGBA")
            else:
                if img.mode != "RGB":
                    img = img.convert("RGB")

            w, h = img.size
            if max(w, h) > MAX_PROOF_EDGE_PX:
                img.thumbnail(
                    (MAX_PROOF_EDGE_PX, MAX_PROOF_EDGE_PX),
                    Image.Resampling.LANCZOS,
                )

            img = _strip_metadata(img)

            buffer = io.BytesIO()
            if ext == ".png":
                img.save(buffer, format="PNG", optimize=True)
                content_type = "image/png"
                out_name = Path(name).with_suffix(".png").name
            else:
                img.save(
                    buffer,
                    format="JPEG",
                    quality=JPEG_QUALITY,
                    optimize=True,
                )
                content_type = "image/jpeg"
                out_name = Path(name).with_suffix(".jpg").name
    except (UnidentifiedImageError, OSError, ProofImageError) as exc:
        raise ProofImageError(FRIENDLY_CORRUPT_MESSAGE) from exc

    return SimpleUploadedFile(out_name, buffer.getvalue(), content_type=content_type)
