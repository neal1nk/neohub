from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile

from .models import Assignment, Submission
from .notifications import notify_teachers_about_submission
from .services import run_assignment_automation


def _active_credit_for(user):
    if not user.is_authenticated:
        return None
    profile = getattr(user, "profile", None)
    if not profile or profile.role != Profile.Role.STUDENT:
        return None
    now = timezone.now()
    return (
        Assignment.objects.filter(
            student=user,
            assignment_type=Assignment.AssignmentType.CREDIT,
            submission_obj__exam_started_at__isnull=False,
            submission_obj__exam_ends_at__gt=now,
            submission_obj__submitted_at__isnull=True,
        )
        .select_related("submission_obj")
        .first()
    )


def _finalize_expired_for_user(user):
    now = timezone.now()
    qs = Submission.objects.filter(
        assignment__student=user,
        assignment__assignment_type=Assignment.AssignmentType.CREDIT,
        exam_started_at__isnull=False,
        exam_ends_at__lte=now,
        submitted_at__isnull=True,
    ).select_related("assignment")
    for submission in qs:
        submission.submitted_at = now
        submission.save(update_fields=["submitted_at"])
        notify_teachers_about_submission(submission.assignment, user)


def _path_allowed_during_exam(path: str, assignment_id: int) -> bool:
    exam_url = reverse("classroom:assignment_submit", args=[assignment_id])
    allowed = [
        exam_url,
        reverse("classroom:credit_autosave", args=[assignment_id]),
        reverse("classroom:credit_upload", args=[assignment_id]),
        reverse("classroom:credit_finish", args=[assignment_id]),
        reverse("classroom:credit_start", args=[assignment_id]),
    ]
    if any(path.startswith(u) for u in allowed):
        return True
    if path.startswith("/logout") or path.rstrip("/").endswith("logout"):
        return True
    if path.startswith("/static/") or path.startswith("/media/"):
        return True
    if path.startswith(reverse("classroom:notifications_poll")):
        return True
    if path.startswith(reverse("classroom:student_assignments_poll")):
        return True
    # Only files belonging to this credit (checked loosely by prefix; views still auth)
    if f"/classroom/files/assignment/" in path:
        return True
    if f"/classroom/files/submission/" in path:
        return True
    return False


class AssignmentAutomationMiddleware:
    """Run overdue/unlock processing and keep students inside active credit exams."""

    _last_run = None
    _interval_seconds = 30

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        request.active_credit = None

        if user and user.is_authenticated:
            now = timezone.now()
            last = AssignmentAutomationMiddleware._last_run
            if last is None or (now - last).total_seconds() >= self._interval_seconds:
                AssignmentAutomationMiddleware._last_run = now
                try:
                    run_assignment_automation()
                except Exception:
                    pass

            try:
                _finalize_expired_for_user(user)
            except Exception:
                pass

            try:
                active = _active_credit_for(user)
            except Exception:
                active = None

            request.active_credit = active
            if active and request.method == "GET":
                if not _path_allowed_during_exam(request.path, active.pk):
                    return redirect("classroom:assignment_submit", assignment_id=active.pk)

        return self.get_response(request)
