from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse


def home(request):
    if request.user.is_authenticated:
        if getattr(request.user, "is_staff_role", False):
            return redirect("staff_home")
        return redirect("app_home")
    return render(
        request,
        "core/landing.html",
        {
            "how_steps": [
                {
                    "title": "Design",
                    "body": "Mock up your garment in the editor. Drafts stay private until you submit.",
                },
                {
                    "title": "Submit",
                    "body": "Send a job request. We confirm details and start the payment window.",
                },
                {
                    "title": "Pay P2P",
                    "body": f"Transfer to GCash, Maya, or bank within {settings.PAYMENT_WINDOW_MINUTES} minutes, then upload proof.",
                },
                {
                    "title": "Produce",
                    "body": "We move your order through edit, production, and completion — tracked in your app.",
                },
            ],
            "gallery_items": [
                {"label": "Aa", "title": "Campus tee", "caption": "Serif lockup on black"},
                {"label": "02", "title": "Event hoodie", "caption": "Two-color crest"},
                {"label": "✦", "title": "Club batch", "caption": "Minimal mark"},
                {"label": "B", "title": "Brand drop", "caption": "Wordmark front"},
                {"label": "24", "title": "Batch run", "caption": "Numbered sleeve"},
                {"label": "◎", "title": "Photo print", "caption": "Full-front graphic"},
            ],
            "testimonials": [
                {
                    "quote": "The mock-up made approvals painless. We knew exactly what we were ordering.",
                    "name": "Mara, org lead",
                },
                {
                    "quote": "P2P payment was clear — upload proof and the status updated fast.",
                    "name": "Jonas, small brand",
                },
                {
                    "quote": "Messenger support answered sizing questions the same afternoon.",
                    "name": "Elle, customer",
                },
            ],
            "faqs": [
                {
                    "q": "How do payments work?",
                    "a": (
                        "1) Submit your design. 2) We share the agreed total and an active payment channel "
                        f"(GCash, Maya, or bank). 3) You transfer within {settings.PAYMENT_WINDOW_MINUTES} minutes. "
                        "4) Upload proof of payment. Money never touches Blytz — we only record claimed payments."
                    ),
                },
                {
                    "q": "What is your refund policy?",
                    "a": (
                        "Strictly no refunds. All sales are final once you submit payment proof. "
                        "Please review your mock-up carefully before paying."
                    ),
                },
                {
                    "q": "Can I edit after submitting?",
                    "a": "Staff may move an order to Pending Edit if changes are needed. Message us on Messenger for urgent fixes.",
                },
                {
                    "q": "Is my draft public?",
                    "a": "No. Unsubmitted designs are incomplete drafts only you can see.",
                },
            ],
            "login_url": reverse("account_login"),
        },
    )


def _require_debug():
    if not settings.DEBUG:
        raise Http404()


def components_gallery(request):
    _require_debug()
    return render(
        request,
        "core/components_gallery.html",
        {
            "select_options": [
                {"value": "s", "label": "Small"},
                {"value": "m", "label": "Medium"},
                {"value": "l", "label": "Large"},
            ],
            "demo_tabs": [
                {
                    "key": "overview",
                    "label": "Overview",
                    "content": "Black and white by default. Gold is an optional accent only.",
                },
                {
                    "key": "usage",
                    "label": "Usage",
                    "content": "Include partials from templates/components/ and pass vars with include ... with.",
                },
                {
                    "key": "a11y",
                    "label": "Focus",
                    "content": "Interactive controls use visible focus-visible rings on ink.",
                },
            ],
            "demo_steps": [
                {"label": "Design", "description": "Pick or upload"},
                {"label": "Order", "description": "Confirm details"},
                {"label": "Pay", "description": f"{settings.PAYMENT_WINDOW_MINUTES} min window"},
                {"label": "Done", "description": "Fulfillment"},
            ],
            "table_headers": ["Order", "Customer", "Status", "Total"],
            "table_rows": [
                ["#1042", "Ada L.", "Pending", "₱1,200"],
                ["#1041", "Kai M.", "Paid", "₱890"],
                ["#1040", "Rio S.", "Shipped", "₱2,450"],
            ],
            "demo_messages": [
                {"level": "info", "text": "Informational message"},
                {"level": "success", "text": "Order confirmed"},
                {"level": "warning", "text": "Payment window closing soon"},
                {"level": "error", "text": "Upload failed — try again"},
            ],
        },
    )


def components_gallery_customer(request):
    _require_debug()
    return render(request, "core/components_gallery_customer.html")


def components_gallery_staff(request):
    _require_debug()
    return render(request, "core/components_gallery_staff.html")
