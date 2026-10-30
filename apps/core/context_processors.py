from django.conf import settings


def blytz(request):
    username = settings.MESSENGER_PAGE_USERNAME or ""
    return {
        "MESSENGER_PAGE_USERNAME": username,
        "messenger_url": f"https://m.me/{username}" if username else "",
        "PAYMENT_WINDOW_MINUTES": settings.PAYMENT_WINDOW_MINUTES,
        "PROOF_MAX_UPLOAD_MB": settings.PROOF_MAX_UPLOAD_MB,
        "DEBUG": settings.DEBUG,
    }
