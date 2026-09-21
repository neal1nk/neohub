def profile_context(request):
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).count()
        return {
            "user_profile": getattr(request.user, "profile", None),
            "unread_notifications": unread,
            "active_credit": getattr(request, "active_credit", None),
            "exam_lock": bool(getattr(request, "active_credit", None)),
        }
    return {
        "user_profile": None,
        "unread_notifications": 0,
        "active_credit": None,
        "exam_lock": False,
    }
