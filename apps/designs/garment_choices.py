"""
Garment template and color allow-lists for Design save/submit.

Must stay aligned with static/js/editor_garments.js GARMENT_TYPES / GARMENT_COLORS
(ids only; grey is a client alias for gray and is not accepted on the server).
"""

# Cross-ref: static/js/editor_garments.js GARMENT_TYPES ids (order must match)
GARMENT_TEMPLATE_IDS = ("tee", "polo", "hoodie", "jersey")

# Load-time aliases → canonical ids. Applied by data migration and JS normalizeGarmentId.
# Unknown keys remain rejected by forms (aliases are not accepted on save).
GARMENT_TEMPLATE_ALIASES = {
    "t-shirt": "tee",
    "tshirt": "tee",
    "t shirt": "tee",
    "polo-shirt": "polo",
    "poloshirt": "polo",
    "sweatshirt": "hoodie",
    "hooded": "hoodie",
}

# Cross-ref: static/js/editor_garments.js GARMENT_COLORS ids (canonical)
GARMENT_COLOR_IDS = (
    "white",
    "black",
    "gray",
    "navy",
    "red",
    "royal",
    "green",
    "yellow",
    "orange",
    "maroon",
)

GARMENT_TEMPLATE_CHOICES = [(x, x) for x in GARMENT_TEMPLATE_IDS]
GARMENT_COLOR_CHOICES = [(x, x) for x in GARMENT_COLOR_IDS]

# Display labels aligned with static/js/editor_garments.js (not stored values).
GARMENT_TEMPLATE_LABELS = {
    "tee": "T-shirt",
    "polo": "Polo shirt",
    "hoodie": "Hoodie",
    "jersey": "Jersey",
}
GARMENT_COLOR_LABELS = {
    "white": "White",
    "black": "Black",
    "gray": "Gray",
    "navy": "Navy",
    "red": "Red",
    "royal": "Royal",
    "green": "Green",
    "yellow": "Yellow",
    "orange": "Orange",
    "maroon": "Maroon",
}


def format_garment_display(template: str | None, color: str | None) -> str:
    """Human-readable garment line for customer lists. Unknown ids stay visible."""
    t_raw = (template or "").strip()
    c_raw = (color or "").strip()
    if not t_raw and not c_raw:
        return "—"
    t = GARMENT_TEMPLATE_LABELS.get(t_raw, t_raw or "—")
    c = GARMENT_COLOR_LABELS.get(c_raw, c_raw or "—")
    return f"{t} · {c}"


def normalize_garment_template(value):
    """Map a stored/legacy key to a canonical template id, or None if unknown."""
    if value in (None, ""):
        return None
    key = str(value).strip().lower()
    if key in GARMENT_TEMPLATE_IDS:
        return key
    aliased = GARMENT_TEMPLATE_ALIASES.get(key)
    if aliased in GARMENT_TEMPLATE_IDS:
        return aliased
    return None


def views_have_objects(views) -> bool:
    if not isinstance(views, dict):
        return False
    for value in views.values():
        if (
            isinstance(value, dict)
            and isinstance(value.get("objects"), list)
            and len(value["objects"]) > 0
        ):
            return True
    return False


def apply_stale_client_views_guard(incoming: dict, stored) -> dict:
    """
    When schema_version is 1 and the client omits "views" while the stored design
    has a views key with at least one object in any view, keep the stored views.
    Explicit views (even empty) overwrite.
    Non-v1 payloads are returned unchanged (opaque).
    """
    if not isinstance(incoming, dict) or incoming.get("schema_version") != 1:
        return incoming
    if "views" in incoming:
        return incoming
    stored_dict = stored if isinstance(stored, dict) else {}
    stored_views = stored_dict.get("views")
    if views_have_objects(stored_views):
        merged = dict(incoming)
        merged["views"] = stored_views
        return merged
    return incoming
