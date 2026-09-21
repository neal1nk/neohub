from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from .models import Notification


def notify(recipient: User, *, kind: str, title: str, message: str = "", link: str = ""):
    return Notification.objects.create(
        recipient=recipient,
        kind=kind,
        title=title,
        message=message,
        link=link,
    )


def notify_teachers_about_submission(assignment, student):
    teacher = getattr(student.profile, "teacher", None)
    if not teacher:
        return
    link = reverse("classroom:assignment_grade", args=[assignment.pk])
    title = f"Сдана работа: {assignment.title}"
    message = (
        f"{student.profile.get_display_name()} отправил(а) "
        f"{assignment.get_assignment_type_display()}."
    )
    notify(
        teacher,
        kind=Notification.Kind.SUBMISSION,
        title=title,
        message=message,
        link=link,
    )


def notify_student_material(student, material):
    notify(
        student,
        kind=Notification.Kind.MATERIAL,
        title=f"Новая теория: {material.title}",
        message="Преподаватель добавил теоретический материал.",
        link=reverse("classroom:student_materials"),
    )


def notify_student_material_updated(student, material):
    notify(
        student,
        kind=Notification.Kind.MATERIAL,
        title=f"Теория обновлена: {material.title}",
        message="Преподаватель изменил теоретический материал.",
        link=reverse("classroom:student_materials"),
    )


def notify_student_assignment(student, assignment):
    """Notify only when the assignment is open (visible) to the student."""
    if assignment.is_closed:
        return
    notify_student_assignment_opened(student, assignment)


def notify_student_assignment_opened(student, assignment):
    grade_note = (
        "Задание на оценку."
        if assignment.is_for_grade
        else "Задание не на оценку."
    )
    deadline_note = ""
    if assignment.deadline:
        deadline_note = f" Дедлайн: {assignment.deadline.strftime('%d.%m.%Y %H:%M')}."
    notify(
        student,
        kind=Notification.Kind.ASSIGNMENT_OPEN,
        title=f"Открыто задание: {assignment.title}",
        message=(
            f"{assignment.get_assignment_type_display()}. {grade_note}{deadline_note}"
        ),
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_assignment_updated(student, assignment):
    if assignment.is_closed:
        return
    notify(
        student,
        kind=Notification.Kind.ASSIGNMENT,
        title=f"Задание обновлено: {assignment.title}",
        message=f"Преподаватель изменил содержание {assignment.get_assignment_type_display().lower()}.",
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_assignment_closed(student, assignment):
    when = ""
    if assignment.unlock_at:
        when = timezone.localtime(assignment.unlock_at).strftime("%d.%m.%Y %H:%M")
    message = "Преподаватель закрыл задание."
    if when:
        message = f"Преподаватель закрыл задание. Автооткрытие: {when}."
    notify(
        student,
        kind=Notification.Kind.ASSIGNMENT,
        title=f"Задание закрыто: {assignment.title}",
        message=message,
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_assignment_files_updated(student, assignment):
    if assignment.is_closed:
        return
    notify(
        student,
        kind=Notification.Kind.ASSIGNMENT,
        title=f"Файлы обновлены: {assignment.title}",
        message="Преподаватель изменил файлы задания.",
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_deadline_changed(student, assignment):
    if assignment.is_closed:
        return
    if assignment.deadline:
        when = timezone.localtime(assignment.deadline).strftime("%d.%m.%Y %H:%M")
        message = f"Новый дедлайн: {when}."
        title = f"Дедлайн изменён: {assignment.title}"
    else:
        message = "Дедлайн снят."
        title = f"Дедлайн снят: {assignment.title}"
    notify(
        student,
        kind=Notification.Kind.ASSIGNMENT,
        title=title,
        message=message,
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_assignment_edit_changes(
    student,
    assignment,
    *,
    was_closed: bool,
    deadline_changed: bool,
    content_changed: bool,
    files_changed: bool,
    unlock_changed: bool = False,
):
    """Send precise notifications for what actually changed in assignment edit."""
    now_closed = assignment.is_closed

    if was_closed and not now_closed:
        notify_student_assignment_opened(student, assignment)
        return

    if not was_closed and now_closed:
        notify_student_assignment_closed(student, assignment)
        return

    if now_closed:
        # Still closed: student cannot open it; only mention schedule change.
        if unlock_changed:
            notify_student_assignment_closed(student, assignment)
        return

    if deadline_changed:
        notify_student_deadline_changed(student, assignment)
    if files_changed:
        notify_student_assignment_files_updated(student, assignment)
    if content_changed:
        notify_student_assignment_updated(student, assignment)


def notify_student_deadline_extended(student, assignment):
    when = ""
    if assignment.deadline:
        when = timezone.localtime(assignment.deadline).strftime("%d.%m.%Y %H:%M")
    notify(
        student,
        kind=Notification.Kind.ASSIGNMENT,
        title=f"Дедлайн продлён: {assignment.title}",
        message=(
            f"Преподаватель продлил дедлайн"
            + (f" до {when}." if when else ".")
        ),
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_grade(student, assignment, *, changed: bool = False):
    from .models import Submission

    submission = (
        Submission.objects.select_related("assignment")
        .filter(assignment=assignment)
        .first()
    )
    if not submission or not submission.is_graded:
        return

    type_label = assignment.get_assignment_type_display().lower()
    grade_text = submission.display_grade()

    if changed:
        title = "Оценка изменена"
        message = (
            f"Оценка изменена за {type_label} «{assignment.title}»: "
            f"теперь {grade_text}."
        )
    else:
        title = f"Выставлена оценка за {type_label}"
        message = (
            f"Выставлена оценка за {type_label} «{assignment.title}»: "
            f"{grade_text}."
        )
    notify(
        student,
        kind=Notification.Kind.GRADE,
        title=title,
        message=message,
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_student_grade_reply(student, assignment):
    notify(
        student,
        kind=Notification.Kind.GRADE,
        title=f"Пояснение к оценке: {assignment.title}",
        message="Преподаватель пояснил оценку.",
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )


def notify_teachers_grade_feedback(assignment, student, *, clarify: bool = True):
    teacher = getattr(student.profile, "teacher", None)
    if not teacher:
        return
    link = reverse("classroom:assignment_grade", args=[assignment.pk])
    name = student.profile.get_display_name()
    title = f"Просят пояснить оценку: {assignment.title}"
    message = f"{name} просит пояснить оценку."
    notify(
        teacher,
        kind=Notification.Kind.GRADE_QUESTION,
        title=title,
        message=message,
        link=link,
    )


def notify_student_credit_retake(student, assignment):
    notify(
        student,
        kind=Notification.Kind.RETAKE,
        title=f"Разрешена пересдача: {assignment.title}",
        message="Преподаватель открыл повторную сдачу зачёта. Можно начать заново.",
        link=reverse("classroom:assignment_submit", args=[assignment.pk]),
    )
