"""Background-ish automation for assignments: overdue zeroing and scheduled unlock."""

from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile

from .models import Assignment, Notification, Submission
from .notifications import notify


def process_overdue_assignments(now=None):
    """Auto-grade overdue for-grade assignments with 0 and notify both sides."""
    now = now or timezone.now()
    qs = (
        Assignment.objects.filter(
            is_for_grade=True,
            overdue_processed=False,
            deadline__isnull=False,
            deadline__lt=now,
        )
        .exclude(submission_obj__submitted_at__isnull=False)
        .filter(Q(submission_obj__isnull=True) | Q(submission_obj__grade__isnull=True))
        .select_related("student", "student__profile", "submission_obj")
    )

    processed = 0

    for assignment in qs:
        submission, _ = Submission.objects.get_or_create(assignment=assignment)
        # Skip if already graded (race) or already submitted and teacher graded
        if submission.grade is not None:
            assignment.overdue_processed = True
            assignment.save(update_fields=["overdue_processed", "updated_at"])
            continue

        submission.grade = 0
        submission.formal_grade = ""
        submission.graded_at = now
        if not submission.teacher_comment:
            submission.teacher_comment = "Автоматически: дедлайн истёк (0 баллов)."
        submission.save()

        assignment.overdue_processed = True
        assignment.save(update_fields=["overdue_processed", "updated_at"])

        student_link = reverse("classroom:assignment_submit", args=[assignment.pk])
        teacher_link = reverse("classroom:assignment_grade", args=[assignment.pk])
        title = f"Просрочено: {assignment.title}"
        student_msg = (
            f"Дедлайн по «{assignment.title}» истёк. "
            f"Выставлено 0 баллов."
        )
        teacher_msg = (
            f"У {assignment.student.profile.get_display_name()} истёк дедлайн "
            f"по «{assignment.title}». Автоматически выставлено 0 баллов."
        )

        notify(
            assignment.student,
            kind=Notification.Kind.OVERDUE,
            title=title,
            message=student_msg,
            link=student_link,
        )
        owner = getattr(assignment.student.profile, "teacher", None)
        if owner:
            notify(
                owner,
                kind=Notification.Kind.OVERDUE,
                title=title,
                message=teacher_msg,
                link=teacher_link,
            )
        processed += 1

    return processed


def process_scheduled_unlocks(now=None):
    """Open closed assignments whose unlock_at has arrived; notify student only about opening."""
    now = now or timezone.now()
    qs = (
        Assignment.objects.filter(is_closed=True, unlock_at__isnull=False, unlock_at__lte=now)
        .select_related("student", "student__profile")
    )
    opened = 0
    for assignment in qs:
        assignment.is_closed = False
        assignment.unlock_at = None
        assignment.save(update_fields=["is_closed", "unlock_at", "updated_at"])
        notify(
            assignment.student,
            kind=Notification.Kind.ASSIGNMENT_OPEN,
            title=f"Открыто задание: {assignment.title}",
            message=(
                f"Доступно: {assignment.get_assignment_type_display()} «{assignment.title}»."
            ),
            link=reverse("classroom:assignment_submit", args=[assignment.pk]),
        )
        opened += 1
    return opened


def run_assignment_automation():
    return {
        "overdue": process_overdue_assignments(),
        "unlocked": process_scheduled_unlocks(),
    }
