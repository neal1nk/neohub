def upload_limits(request):
    from .uploads import ACCEPT_ATTR, MAX_UPLOAD_BYTES, UPLOAD_HINT

    return {
        "upload_accept": ACCEPT_ATTR,
        "upload_hint": UPLOAD_HINT,
        "upload_max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }
