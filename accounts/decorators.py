from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Profile


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            profile = getattr(request.user, "profile", None)
            if profile is None or profile.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


teacher_required = role_required(Profile.Role.TEACHER)
student_required = role_required(Profile.Role.STUDENT)


def redirect_by_role(user):
    profile = getattr(user, "profile", None)
    if profile and profile.is_teacher:
        return redirect("classroom:teacher_dashboard")
    return redirect("classroom:student_dashboard")
