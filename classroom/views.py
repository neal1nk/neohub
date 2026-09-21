from pathlib import Path
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import student_required, teacher_required
from accounts.forms import CreateStudentForm, StudentPersonalDataForm
from accounts.models import Profile

from .forms import (
    AssignmentForm,
    ExtendDeadlineForm,
    FormalGradeForm,
    GradeClarifyForm,
    GradeFeedbackForm,
    GradeForm,
    MaterialForm,
    SubmissionForm,
)
from .models import (
    Assignment,
    AssignmentFile,
    Material,
    MaterialFile,
    Notification,
    Submission,
    SubmissionFile,
)
from .notifications import (
    notify_student_assignment,
    notify_student_assignment_closed,
    notify_student_assignment_edit_changes,
    notify_student_assignment_opened,
    notify_student_credit_retake,
    notify_student_deadline_extended,
    notify_student_grade,
    notify_student_grade_reply,
    notify_student_material,
    notify_student_material_updated,
    notify_teachers_about_submission,
    notify_teachers_grade_feedback,
)


def _students_qs(teacher):
    return (
        User.objects.filter(
            profile__role=Profile.Role.STUDENT,
            profile__teacher=teacher,
        )
        .select_related("profile")
        .order_by("profile__display_name", "username")
    )


def _get_student(student_id: int, teacher) -> User:
    return get_object_or_404(
        User.objects.select_related("profile"),
        pk=student_id,
        profile__role=Profile.Role.STUDENT,
        profile__teacher=teacher,
    )


def _teacher_owns_student(teacher, student) -> bool:
    profile = getattr(student, "profile", None)
    return bool(
        profile
        and profile.role == Profile.Role.STUDENT
        and profile.teacher_id == teacher.id
    )


def _get_teacher_assignment(assignment_id: int, teacher) -> Assignment:
    return get_object_or_404(
        Assignment.objects.select_related(
            "student", "student__profile", "submission_obj"
        ),
        pk=assignment_id,
        student__profile__role=Profile.Role.STUDENT,
        student__profile__teacher=teacher,
    )


def _get_teacher_material(material_id: int, teacher) -> Material:
    return get_object_or_404(
        Material.objects.select_related("student", "student__profile").prefetch_related(
            "files"
        ),
        pk=material_id,
        student__profile__role=Profile.Role.STUDENT,
        student__profile__teacher=teacher,
    )


def _student_tab_url(student_id: int, tab: str) -> str:
    return f"{reverse('classroom:student_detail', args=[student_id])}?tab={tab}"


def _save_uploaded_files(files, model_cls, *, teacher=None, copies: int = 1, **fk_kwargs):
    from .storage_quota import check_teacher_storage_quota
    from .uploads import filter_valid_uploads

    valid, errors = filter_valid_uploads(files)
    if not valid:
        return [], errors
    quota_error = check_teacher_storage_quota(teacher, valid, copies=copies)
    if quota_error:
        return [], errors + [quota_error]
    created = []
    for uploaded in valid:
        created.append(
            model_cls.objects.create(
                file=uploaded,
                original_name=uploaded.name,
                **fk_kwargs,
            )
        )
    return created, errors


def _teacher_for_student(student) -> User | None:
    profile = getattr(student, "profile", None)
    return getattr(profile, "teacher", None) if profile else None


def _submission_file_payload(item: SubmissionFile) -> dict:
    return {
        "id": item.id,
        "name": item.original_name or item.file.name,
        "url": reverse("classroom:download_submission_file", args=[item.id]),
        "deleteUrl": reverse("classroom:submission_file_delete", args=[item.id]),
    }


def _student_assignments_url(assignment_type: str | None = None) -> str:
    url = reverse("classroom:student_assignments")
    if assignment_type and assignment_type in Assignment.AssignmentType.values:
        return f"{url}?type={assignment_type}"
    return f"{url}?type=all"


def _upcoming_assignments(student, limit=5):
    assignments = list(
        student.assignments.select_related("submission_obj").order_by("-created_at")
    )
    upcoming = [
        a
        for a in assignments
        if a.compute_status() in (Assignment.Status.OPEN, Assignment.Status.OVERDUE)
    ]
    return upcoming[:limit]


def _pending_submissions_qs(teacher):
    return (
        Submission.objects.filter(
            submitted_at__isnull=False,
            assignment__student__profile__teacher=teacher,
        )
        .filter(
            Q(assignment__is_for_grade=True, grade__isnull=True)
            | Q(assignment__is_for_grade=False, formal_grade="")
        )
        .select_related(
            "assignment",
            "assignment__student",
            "assignment__student__profile",
        )
        .order_by("-submitted_at")
    )


@teacher_required
def teacher_dashboard(request):
    from .storage_quota import teacher_storage_stats

    students = _students_qs(request.user)
    pending_qs = _pending_submissions_qs(request.user)
    return render(
        request,
        "classroom/teacher_dashboard.html",
        {
            "students": students,
            "student_count": students.count(),
            "pending_grades": pending_qs.count(),
            "pending_items": pending_qs[:100],
            "storage": teacher_storage_stats(request.user),
        },
    )


@teacher_required
@require_http_methods(["GET", "POST"])
def assignment_bulk_create(request):
    students = list(_students_qs(request.user))
    assignment_type = request.POST.get("assignment_type") or request.GET.get(
        "type", Assignment.AssignmentType.HOMEWORK
    )
    if assignment_type not in Assignment.AssignmentType.values:
        assignment_type = Assignment.AssignmentType.HOMEWORK

    form = AssignmentForm(
        request.POST or None,
        assignment_type=assignment_type,
    )

    if request.method == "POST":
        selected_ids = [int(x) for x in request.POST.getlist("students") if str(x).isdigit()]
        selected = [s for s in students if s.pk in selected_ids]
        files = request.FILES.getlist("files")
        is_for_grade = request.POST.get("submit_action") != "ungraded"
        if assignment_type == Assignment.AssignmentType.CREDIT:
            is_for_grade = True

        if not selected:
            messages.error(request, "Выберите хотя бы одного ученика.")
        elif form.is_valid():
            from django.core.files.base import ContentFile

            from .storage_quota import check_teacher_storage_quota
            from .uploads import filter_valid_uploads

            valid_files, file_errors = filter_valid_uploads(files)
            for err in file_errors:
                messages.error(request, err)

            quota_error = check_teacher_storage_quota(
                request.user, valid_files, copies=len(selected)
            )
            if quota_error:
                messages.error(request, quota_error)
                return redirect("classroom:assignment_bulk_create")

            file_blobs = []
            for uploaded in valid_files:
                file_blobs.append((uploaded.name, uploaded.read()))

            created = 0
            for student in selected:
                assignment = Assignment(
                    student=student,
                    assignment_type=assignment_type,
                    title=form.cleaned_data["title"],
                    description=form.cleaned_data.get("description") or "",
                    instruction=form.cleaned_data.get("instruction") or "",
                    duration_minutes=form.cleaned_data.get("duration_minutes"),
                    deadline=form.cleaned_data.get("deadline"),
                    is_closed=bool(form.cleaned_data.get("is_closed")),
                    unlock_at=form.cleaned_data.get("unlock_at"),
                    is_for_grade=is_for_grade,
                    created_by=request.user,
                )
                if assignment.unlock_at and not assignment.is_closed:
                    assignment.is_closed = True
                assignment.save()
                for name, data in file_blobs:
                    AssignmentFile.objects.create(
                        assignment=assignment,
                        file=ContentFile(data, name=name),
                        original_name=name,
                    )
                notify_student_assignment(student, assignment)
                created += 1
            messages.success(
                request,
                f"Задание «{form.cleaned_data['title']}» выдано {created} уч.",
            )
            return redirect("classroom:teacher_dashboard")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)

    return render(
        request,
        "classroom/assignment_bulk.html",
        {
            "students": students,
            "form": form,
            "assignment_type": assignment_type,
            "type_choices": Assignment.AssignmentType.choices,
        },
    )


@teacher_required
@require_http_methods(["GET", "POST"])
def student_create(request):
    form = CreateStudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(teacher=request.user)
        name = user.profile.get_display_name()
        messages.success(
            request,
            f"Ученик «{name}» создан. Логин: {user.username}",
        )
        return redirect("classroom:student_detail", student_id=user.pk)
    return render(request, "classroom/student_create.html", {"form": form})


@teacher_required
@require_http_methods(["GET", "POST"])
def student_detail(request, student_id: int):
    student = _get_student(student_id, request.user)
    tab = request.GET.get("tab", "overview")
    valid_tabs = {"overview", "theory", "homework", "practice", "credit", "profile"}

    personal_form = StudentPersonalDataForm(student=student)
    if request.method == "POST" and (
        tab == "profile" or "max_messenger" in request.POST or "telegram" in request.POST
    ):
        tab = "profile"
        personal_form = StudentPersonalDataForm(request.POST, student=student)
        if personal_form.is_valid():
            personal_form.save()
            messages.success(request, "Личные данные обновлены.")
            return redirect(_student_tab_url(student_id, "profile"))

    if tab not in valid_tabs:
        tab = "overview"

    rating = student.profile.rating_score()
    study_stats = student.profile.study_stats()
    return render(
        request,
        "classroom/student_detail.html",
        {
            "student": student,
            "tab": tab,
            "rating": rating,
            "rating_color": student.profile.rating_color(),
            "rating_breakdown_text": student.profile.rating_breakdown_text(),
            "study_stats": study_stats,
            "upcoming": _upcoming_assignments(student, limit=5),
            "materials": student.materials.prefetch_related("files").all(),
            "homework_list": student.assignments.filter(
                assignment_type=Assignment.AssignmentType.HOMEWORK
            )
            .select_related("submission_obj")
            .prefetch_related("files", "submission_obj__files")
            .order_by("-created_at"),
            "practice_list": student.assignments.filter(
                assignment_type=Assignment.AssignmentType.PRACTICE
            )
            .select_related("submission_obj")
            .prefetch_related("files", "submission_obj__files")
            .order_by("-created_at"),
            "credit_list": student.assignments.filter(
                assignment_type=Assignment.AssignmentType.CREDIT
            )
            .select_related("submission_obj")
            .prefetch_related("files", "submission_obj__files")
            .order_by("-created_at"),
            "material_form": MaterialForm(),
            "assignment_form": AssignmentForm(
                assignment_type=tab
                if tab in Assignment.AssignmentType.values
                else None
            ),
            "personal_form": personal_form,
        },
    )


@teacher_required
@require_POST
def assignment_create(request, student_id: int, assignment_type: str):
    student = _get_student(student_id, request.user)
    if assignment_type not in Assignment.AssignmentType.values:
        messages.error(request, "Неизвестный тип задания.")
        return redirect("classroom:student_detail", student_id=student_id)

    form = AssignmentForm(request.POST, assignment_type=assignment_type)
    files = request.FILES.getlist("files")
    is_for_grade = request.POST.get("submit_action") != "ungraded"
    if assignment_type == Assignment.AssignmentType.CREDIT:
        is_for_grade = True

    if form.is_valid():
        assignment = form.save(commit=False)
        assignment.student = student
        assignment.assignment_type = assignment_type
        assignment.created_by = request.user
        assignment.is_for_grade = is_for_grade
        if assignment.unlock_at and not assignment.is_closed:
            assignment.is_closed = True
        assignment.save()
        saved_files, file_errors = _save_uploaded_files(
            files, AssignmentFile, teacher=request.user, assignment=assignment
        )
        for err in file_errors:
            messages.error(request, err)
        # Уведомление только при открытии (сразу, если не закрыто)
        notify_student_assignment(student, assignment)
        if assignment.is_closed:
            when = (
                assignment.unlock_at.strftime("%d.%m.%Y %H:%M")
                if assignment.unlock_at
                else "вручную"
            )
            messages.success(
                request,
                f"Задание создано закрытым (откроется: {when})"
                f"{f' · файлов: {len(saved_files)}' if saved_files else ''}.",
            )
        elif is_for_grade:
            messages.success(
                request,
                f"Задание создано{f' · файлов: {len(saved_files)}' if saved_files else ''}.",
            )
        else:
            messages.success(
                request,
                f"Задание без оценки создано{f' · файлов: {len(saved_files)}' if saved_files else ''}.",
            )
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(_student_tab_url(student_id, assignment_type))


@teacher_required
@require_http_methods(["GET", "POST"])
def assignment_edit(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related(
            "student", "student__profile", "submission_obj"
        ).prefetch_related("files"),
        pk=assignment_id,
        student__profile__teacher=request.user,
    )
    submission = getattr(assignment, "submission_obj", None)
    if submission and submission.is_submitted:
        messages.error(
            request,
            "Нельзя изменить задание: работа уже отправлена на проверку.",
        )
        return redirect(
            _student_tab_url(assignment.student_id, assignment.assignment_type)
        )
    form = AssignmentForm(
        request.POST or None,
        instance=assignment,
        assignment_type=assignment.assignment_type,
    )
    # Snapshot BEFORE is_valid(): ModelForm._post_clean mutates instance in-place.
    was_closed = assignment.is_closed
    old_deadline = assignment.deadline
    old_unlock = assignment.unlock_at
    old_title = assignment.title
    old_description = assignment.description or ""
    old_instruction = assignment.instruction or ""
    old_duration = assignment.duration_minutes

    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        if updated.unlock_at and not updated.is_closed:
            updated.is_closed = True
        updated.save()
        remove_ids = request.POST.getlist("remove_files")
        if remove_ids:
            for item in assignment.files.filter(pk__in=remove_ids):
                if item.file:
                    item.file.delete(save=False)
                item.delete()
        saved_files, file_errors = _save_uploaded_files(
            request.FILES.getlist("files"),
            AssignmentFile,
            teacher=request.user,
            assignment=assignment,
        )
        for err in file_errors:
            messages.error(request, err)

        deadline_changed = old_deadline != updated.deadline
        unlock_changed = old_unlock != updated.unlock_at
        content_changed = (
            old_title != updated.title
            or old_description != (updated.description or "")
            or old_instruction != (updated.instruction or "")
            or old_duration != updated.duration_minutes
        )
        files_changed = bool(remove_ids) or bool(saved_files)

        notify_student_assignment_edit_changes(
            assignment.student,
            updated,
            was_closed=was_closed,
            deadline_changed=deadline_changed,
            content_changed=content_changed,
            files_changed=files_changed,
            unlock_changed=unlock_changed,
        )
        messages.success(
            request,
            f"Задание обновлено{f' · новых файлов: {len(saved_files)}' if saved_files else ''}.",
        )
        return redirect(
            _student_tab_url(assignment.student_id, assignment.assignment_type)
        )
    if request.method == "POST":
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return render(
        request,
        "classroom/assignment_edit.html",
        {
            "assignment": assignment,
            "form": form,
            "student": assignment.student,
        },
    )


@teacher_required
@require_http_methods(["GET", "POST"])
def assignment_grade(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related(
            "student", "student__profile", "submission_obj"
        ).prefetch_related("files", "submission_obj__files"),
        pk=assignment_id,
        student__profile__teacher=request.user,
    )
    submission, _ = Submission.objects.get_or_create(assignment=assignment)

    if assignment.is_for_grade:
        previous_grade = submission.grade
        initial_grade = previous_grade if previous_grade is not None else 0
        form = GradeForm(
            request.POST or None,
            instance=submission,
            initial={"grade": initial_grade},
        )
        if request.method == "POST" and form.is_valid():
            graded = form.save(commit=False)
            graded.formal_grade = ""
            graded.graded_at = timezone.now()
            graded.save()
            Assignment.objects.filter(pk=assignment.pk).update(overdue_processed=True)
            changed = previous_grade is not None and previous_grade != graded.grade
            notify_student_grade(assignment.student, assignment, changed=changed)
            messages.success(request, "Оценка сохранена.")
            return redirect(
                _student_tab_url(assignment.student_id, assignment.assignment_type)
            )
    else:
        previous_formal = submission.formal_grade
        form = FormalGradeForm(request.POST or None, instance=submission)
        if request.method == "POST" and form.is_valid():
            graded = form.save(commit=False)
            graded.grade = None
            graded.graded_at = timezone.now()
            graded.save()
            changed = bool(previous_formal) and previous_formal != graded.formal_grade
            notify_student_grade(assignment.student, assignment, changed=changed)
            messages.success(request, "Формальная оценка сохранена.")
            return redirect(
                _student_tab_url(assignment.student_id, assignment.assignment_type)
            )

    return render(
        request,
        "classroom/assignment_grade.html",
        {
            "assignment": assignment,
            "submission": submission,
            "form": form,
            "is_formal": not assignment.is_for_grade,
        },
    )


def _delete_filefield(field_file) -> None:
    if not field_file:
        return
    try:
        field_file.delete(save=False)
    except Exception:
        pass


def _purge_student_uploaded_files(student: User) -> int:
    """Remove media files belonging to the student from disk before CASCADE delete."""
    removed = 0

    submission_files = SubmissionFile.objects.filter(
        submission__assignment__student=student
    )
    for item in submission_files.iterator():
        _delete_filefield(item.file)
        removed += 1

    assignment_files = AssignmentFile.objects.filter(assignment__student=student)
    for item in assignment_files.iterator():
        _delete_filefield(item.file)
        removed += 1

    material_files = MaterialFile.objects.filter(material__student=student)
    for item in material_files.iterator():
        _delete_filefield(item.file)
        removed += 1

    return removed


@teacher_required
@require_POST
def student_delete(request, student_id: int):
    student = _get_student(student_id, request.user)
    confirm_username = (request.POST.get("confirm_username") or "").strip()
    if confirm_username != student.username:
        messages.error(
            request,
            f"Чтобы удалить ученика, введите логин точно: {student.username}",
        )
        return redirect(_student_tab_url(student_id, "overview"))
    name = student.profile.get_display_name()
    _purge_student_uploaded_files(student)
    student.delete()
    messages.success(request, f"Ученик «{name}» удалён вместе с файлами.")
    return redirect("classroom:teacher_dashboard")


@teacher_required
@require_POST
def material_create(request, student_id: int):
    student = _get_student(student_id, request.user)
    form = MaterialForm(request.POST)
    files = request.FILES.getlist("files")
    if form.is_valid():
        material = form.save(commit=False)
        material.student = student
        material.created_by = request.user
        material.save()
        saved_files, file_errors = _save_uploaded_files(
            files, MaterialFile, teacher=request.user, material=material
        )
        for err in file_errors:
            messages.error(request, err)
        notify_student_material(student, material)
        messages.success(
            request,
            f"Теоретический материал добавлен{f' · файлов: {len(saved_files)}' if saved_files else ''}.",
        )
    else:
        messages.error(request, "Не удалось сохранить материал. Проверьте поля.")
    return redirect(_student_tab_url(student_id, "theory"))


@teacher_required
@require_http_methods(["GET", "POST"])
def material_edit(request, material_id: int):
    material = get_object_or_404(
        Material.objects.select_related("student").prefetch_related("files"),
        pk=material_id,
        student__profile__teacher=request.user,
    )
    form = MaterialForm(request.POST or None, instance=material)
    if request.method == "POST" and form.is_valid():
        form.save()
        remove_ids = request.POST.getlist("remove_files")
        if remove_ids:
            for item in material.files.filter(pk__in=remove_ids):
                if item.file:
                    item.file.delete(save=False)
                item.delete()
        saved_files, file_errors = _save_uploaded_files(
            request.FILES.getlist("files"),
            MaterialFile,
            teacher=request.user,
            material=material,
        )
        for err in file_errors:
            messages.error(request, err)
        notify_student_material_updated(material.student, material)
        messages.success(
            request,
            f"Материал обновлён{f' · новых файлов: {len(saved_files)}' if saved_files else ''}.",
        )
        return redirect(_student_tab_url(material.student_id, "theory"))
    return render(
        request,
        "classroom/material_edit.html",
        {"material": material, "form": form, "student": material.student},
    )


@teacher_required
@require_POST
def material_delete(request, material_id: int):
    material = get_object_or_404(
        Material, pk=material_id, student__profile__teacher=request.user
    )
    student_id = material.student_id
    material.delete()
    messages.success(request, "Материал удалён.")
    return redirect(_student_tab_url(student_id, "theory"))


@teacher_required
@require_POST
def assignment_delete(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment, pk=assignment_id, student__profile__teacher=request.user
    )
    student_id = assignment.student_id
    tab = assignment.assignment_type
    assignment.delete()
    messages.success(request, "Задание удалено.")
    return redirect(_student_tab_url(student_id, tab))


@teacher_required
@require_POST
def assignment_extend_deadline(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj", "student"),
        pk=assignment_id,
        student__profile__teacher=request.user,
    )
    form = ExtendDeadlineForm(
        request.POST, current_deadline=assignment.deadline
    )
    if form.is_valid():
        new_deadline = form.cleaned_data["deadline"]
        if timezone.is_naive(new_deadline):
            new_deadline = timezone.make_aware(
                new_deadline, timezone.get_current_timezone()
            )
        assignment.deadline = new_deadline
        assignment.overdue_processed = False
        assignment.save(update_fields=["deadline", "overdue_processed", "updated_at"])

        submission = getattr(assignment, "submission_obj", None)
        if (
            submission
            and submission.grade == 0
            and submission.teacher_comment
            and "Автоматически: дедлайн" in submission.teacher_comment
        ):
            submission.grade = None
            submission.graded_at = None
            submission.teacher_comment = ""
            submission.save(update_fields=["grade", "graded_at", "teacher_comment"])

        notify_student_deadline_extended(assignment.student, assignment)
        local_deadline = timezone.localtime(assignment.deadline)
        messages.success(
            request,
            f"Дедлайн продлён до {local_deadline.strftime('%d.%m.%Y %H:%M')}.",
        )
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(_student_tab_url(assignment.student_id, assignment.assignment_type))


@teacher_required
@require_POST
def assignment_toggle_lock(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment, pk=assignment_id, student__profile__teacher=request.user
    )
    want_closed = request.POST.get("is_closed") in ("1", "true", "on", "yes")
    unlock_raw = (request.POST.get("unlock_at") or "").strip()
    action = (request.POST.get("lock_action") or "").strip()
    was_closed = assignment.is_closed

    # Explicit open button always wins (even if unlock_at is filled in the form)
    if action == "open":
        want_closed = False

    from django.core.exceptions import ValidationError
    from django.forms.fields import DateTimeField

    def parse_unlock(raw):
        field = DateTimeField(
            input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        )
        return field.clean(raw)

    if not want_closed:
        # Manual open: clear schedule so it stays open
        assignment.is_closed = False
        assignment.unlock_at = None
    else:
        assignment.is_closed = True
        if unlock_raw:
            try:
                assignment.unlock_at = parse_unlock(unlock_raw)
            except ValidationError:
                messages.error(request, "Некорректная дата автооткрытия.")
                return redirect(
                    _student_tab_url(assignment.student_id, assignment.assignment_type)
                )
        else:
            assignment.unlock_at = None

    assignment.save(update_fields=["is_closed", "unlock_at", "updated_at"])

    if was_closed and not assignment.is_closed:
        notify_student_assignment_opened(assignment.student, assignment)
        messages.success(request, "Задание открыто для ученика.")
    elif not was_closed and assignment.is_closed:
        notify_student_assignment_closed(assignment.student, assignment)
        when = (
            assignment.unlock_at.strftime("%d.%m.%Y %H:%M")
            if assignment.unlock_at
            else "только вручную"
        )
        messages.success(request, f"Задание закрыто. Автооткрытие: {when}.")
    elif assignment.is_closed:
        when = (
            assignment.unlock_at.strftime("%d.%m.%Y %H:%M")
            if assignment.unlock_at
            else "только вручную"
        )
        messages.success(request, f"Задание закрыто. Автооткрытие: {when}.")
    else:
        messages.success(request, "Доступ к заданию обновлён.")

    return redirect(_student_tab_url(assignment.student_id, assignment.assignment_type))


@login_required
@require_POST
def notifications_clear(request):
    request.user.notifications.all().delete()
    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        return render(
            request,
            "classroom/_notifications_list_body.html",
            {
                "notifications": [],
                "unread_notifications": 0,
                "swap_badge": True,
                "swap_heading": True,
            },
        )
    messages.success(request, "Уведомления очищены.")
    return redirect("classroom:notifications")


@student_required
def student_dashboard(request):
    assignments = list(
        request.user.assignments.select_related("submission_obj").order_by("-created_at")
    )
    upcoming = [
        a
        for a in assignments
        if not a.is_closed
        and a.compute_status() in (Assignment.Status.OPEN, Assignment.Status.OVERDUE)
    ]
    upcoming.sort(
        key=lambda a: (
            a.deadline is None,
            a.deadline or timezone.now(),
            -a.created_at.timestamp(),
        )
    )
    upcoming = upcoming[:4]

    graded = [
        a for a in assignments if a.compute_status() == Assignment.Status.GRADED
    ]
    graded.sort(
        key=lambda a: (
            (a.submission.graded_at if a.submission else None)
            or (a.submission.submitted_at if a.submission else None)
            or a.updated_at
        ),
        reverse=True,
    )
    recent_graded = graded[:2]

    rating = request.user.profile.rating_score()
    teacher = request.user.profile.teacher
    if teacher is not None:
        teacher = (
            User.objects.select_related("profile").filter(pk=teacher.pk).first()
        )
    return render(
        request,
        "classroom/student_dashboard.html",
        {
            "materials": request.user.materials.all()[:2],
            "upcoming": upcoming,
            "recent_graded": recent_graded,
            "rating": rating,
            "rating_color": request.user.profile.rating_color(),
            "rating_display": rating if rating is not None else 0,
            "rating_breakdown_text": request.user.profile.rating_breakdown_text(),
            "teacher": teacher,
        },
    )


@student_required
def student_materials(request):
    return render(
        request,
        "classroom/student_materials.html",
        {"materials": request.user.materials.prefetch_related("files").all()},
    )


@student_required
def student_assignments(request):
    type_filter = request.GET.get("type", "all")
    qs = (
        request.user.assignments.select_related("submission_obj")
        .prefetch_related("files", "submission_obj__files")
        .order_by("-created_at", "-pk")
    )
    if type_filter in Assignment.AssignmentType.values:
        qs = qs.filter(assignment_type=type_filter)
    assignments = list(qs)
    version = _assignments_version(assignments)
    return render(
        request,
        "classroom/student_assignments.html",
        {
            "assignments": assignments,
            "type_filter": type_filter,
            "list_version": version,
        },
    )


def _assignments_version(assignments) -> str:
    """Stable fingerprint of list state (no time-derived status — avoids poll flicker)."""
    import hashlib

    parts = []
    for a in sorted(assignments, key=lambda x: x.pk):
        sub = a.submission
        parts.append(
            "|".join(
                [
                    str(a.pk),
                    str(int(a.is_closed)),
                    str(a.unlock_at.timestamp() if a.unlock_at else 0),
                    str(a.deadline.timestamp() if a.deadline else 0),
                    str(int(a.overdue_processed)),
                    str(a.updated_at.timestamp() if a.updated_at else 0),
                    str(sub.grade if sub and sub.grade is not None else ""),
                    str(sub.formal_grade if sub else ""),
                    str(sub.submitted_at.timestamp() if sub and sub.submitted_at else 0),
                    str(
                        sub.exam_started_at.timestamp()
                        if sub and sub.exam_started_at
                        else 0
                    ),
                    str(int(bool(sub and sub.clarification_requested))),
                ]
            )
        )
    raw = "\n".join(parts) + f"\ncount={len(assignments)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


@student_required
def student_assignments_poll(request):
    """Return updated assignment cards when list fingerprint changes."""
    type_filter = request.GET.get("type", "all")
    since = (request.GET.get("v") or "").strip()
    qs = (
        request.user.assignments.select_related("submission_obj")
        .prefetch_related("files", "submission_obj__files")
        .order_by("-created_at", "-pk")
    )
    if type_filter in Assignment.AssignmentType.values:
        qs = qs.filter(assignment_type=type_filter)
    assignments = list(qs)
    version = _assignments_version(assignments)
    if since and since == version:
        return JsonResponse({"changed": False, "version": version})

    html = render(
        request,
        "classroom/_assignments_live_body.html",
        {"assignments": assignments, "type_filter": type_filter},
    ).content.decode("utf-8")
    return JsonResponse(
        {
            "changed": True,
            "version": version,
            "html": html,
            "count": len(assignments),
        }
    )


@student_required
@require_http_methods(["GET", "POST"])
def assignment_submit(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj").prefetch_related(
            "files", "submission_obj__files"
        ),
        pk=assignment_id,
        student=request.user,
    )

    if not assignment.is_accessible_to_student():
        messages.error(
            request,
            "Задание закрыто преподавателем. Оно станет доступно после открытия.",
        )
        return redirect(_student_assignments_url(assignment.assignment_type))

    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    _finalize_expired_credit(assignment, submission)

    if assignment.is_credit():
        return _credit_submit_flow(request, assignment, submission)

    locked = assignment.is_locked_for_student()

    if request.method == "POST":
        if locked:
            messages.error(request, "Работа уже отправлена и недоступна для изменения.")
            return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

        files = request.FILES.getlist("files")
        text = request.POST.get("text", submission.text)
        submission.text = text or ""
        has_content = bool(submission.text.strip()) or bool(files) or submission.files.exists()
        if not has_content:
            messages.error(request, "Добавьте текст ответа или файл.")
            form = SubmissionForm(initial={"text": submission.text}, has_files=False)
            return render(
                request,
                "classroom/assignment_submit.html",
                {
                    "assignment": assignment,
                    "form": form,
                    "submission": submission,
                    "locked": False,
                },
            )

        submission.submitted_at = timezone.now()
        submission.save()
        _, file_errors = _save_uploaded_files(
            files,
            SubmissionFile,
            teacher=_teacher_for_student(request.user),
            submission=submission,
        )
        for err in file_errors:
            messages.error(request, err)
        notify_teachers_about_submission(assignment, request.user)
        messages.success(request, "Работа отправлена.")
        return redirect(_student_assignments_url(assignment.assignment_type))

    form = SubmissionForm(
        initial={"text": submission.text if submission else ""},
        has_files=bool(submission and submission.files.exists()),
    )

    return render(
        request,
        "classroom/assignment_submit.html",
        {
            "assignment": assignment,
            "form": form,
            "submission": submission,
            "locked": locked,
        },
    )


@student_required
@require_POST
def grade_feedback(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj"),
        pk=assignment_id,
        student=request.user,
    )
    submission = getattr(assignment, "submission_obj", None)
    if not submission or not submission.is_graded:
        messages.error(request, "Сначала должна появиться оценка.")
        return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

    form = GradeFeedbackForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

    submission.student_comment = form.cleaned_data["student_comment"]
    submission.clarification_requested = True
    submission.save(update_fields=["student_comment", "clarification_requested"])
    notify_teachers_grade_feedback(assignment, request.user)
    messages.success(request, "Запрос на пояснение отправлен преподавателю.")
    return redirect("classroom:assignment_submit", assignment_id=assignment.pk)


@teacher_required
@require_POST
def grade_clarify(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("student", "submission_obj"),
        pk=assignment_id,
        student__profile__teacher=request.user,
    )
    submission = getattr(assignment, "submission_obj", None)
    if not submission or not submission.is_graded:
        messages.error(request, "Сначала выставьте оценку.")
        return redirect("classroom:assignment_grade", assignment_id=assignment.pk)
    if not submission.clarification_requested:
        messages.info(request, "Ученик сейчас не ждёт пояснения.")
        return redirect("classroom:assignment_grade", assignment_id=assignment.pk)

    form = GradeClarifyForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("classroom:assignment_grade", assignment_id=assignment.pk)

    submission.teacher_comment = form.cleaned_data["clarification"]
    submission.clarification_requested = False
    submission.save(update_fields=["teacher_comment", "clarification_requested"])
    notify_student_grade_reply(assignment.student, assignment)
    messages.success(request, "Пояснение отправлено ученику.")
    return redirect(
        _student_tab_url(assignment.student_id, assignment.assignment_type)
    )


@student_required
@require_POST
def assignment_draft_autosave(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment,
        pk=assignment_id,
        student=request.user,
    )
    if assignment.is_credit():
        return JsonResponse({"ok": False, "error": "not_supported"}, status=400)
    if not assignment.is_accessible_to_student():
        return JsonResponse({"ok": False, "error": "closed"}, status=403)
    if assignment.is_locked_for_student():
        return JsonResponse({"ok": False, "error": "locked"}, status=400)

    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    submission.text = request.POST.get("text", submission.text)
    submission.save(update_fields=["text"])
    return JsonResponse({"ok": True, "saved_at": timezone.now().isoformat()})


@student_required
@require_POST
def assignment_draft_upload(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj"),
        pk=assignment_id,
        student=request.user,
    )
    if assignment.is_credit():
        return JsonResponse({"ok": False, "error": "not_supported"}, status=400)
    if not assignment.is_accessible_to_student():
        return JsonResponse({"ok": False, "error": "closed"}, status=403)
    if assignment.is_locked_for_student():
        return JsonResponse({"ok": False, "error": "locked"}, status=400)

    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    files = request.FILES.getlist("files")
    created, errors = _save_uploaded_files(
        files,
        SubmissionFile,
        teacher=_teacher_for_student(request.user),
        submission=submission,
    )
    return JsonResponse(
        {
            "ok": bool(created) or not errors,
            "errors": errors,
            "files": [_submission_file_payload(f) for f in created],
        },
        status=200 if (created or not errors) else 400,
    )


@student_required
@require_POST
def submission_file_delete(request, file_id: int):
    item = get_object_or_404(
        SubmissionFile.objects.select_related("submission__assignment"),
        pk=file_id,
        submission__assignment__student=request.user,
    )
    assignment = item.submission.assignment
    submission = item.submission

    if assignment.is_credit():
        if _finalize_expired_credit(assignment, submission):
            return JsonResponse(
                {
                    "ok": False,
                    "expired": True,
                    "redirect": reverse("classroom:assignment_submit", args=[assignment.pk]),
                }
            )
        if submission.submitted_at or not assignment.is_exam_in_progress():
            return JsonResponse({"ok": False, "error": "exam_not_active"}, status=400)
    else:
        if not assignment.is_accessible_to_student():
            return JsonResponse({"ok": False, "error": "closed"}, status=403)
        if assignment.is_locked_for_student():
            return JsonResponse({"ok": False, "error": "locked"}, status=400)

    if item.file:
        item.file.delete(save=False)
    deleted_id = item.id
    item.delete()
    return JsonResponse({"ok": True, "id": deleted_id})


@teacher_required
@require_POST
def assignment_credit_retake(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj", "student", "student__profile"),
        pk=assignment_id,
        assignment_type=Assignment.AssignmentType.CREDIT,
        student__profile__teacher=request.user,
    )
    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    if not submission.submitted_at and not submission.exam_started_at:
        messages.info(request, "Зачёт ещё не начинали — пересдача не нужна.")
        return redirect(_student_tab_url(assignment.student_id, "credit"))

    # Reset attempt completely
    submission.submitted_at = None
    submission.exam_started_at = None
    submission.exam_ends_at = None
    submission.grade = None
    submission.formal_grade = ""
    submission.graded_at = None
    submission.teacher_comment = ""
    submission.student_comment = ""
    submission.clarification_requested = False
    submission.text = ""
    submission.save()
    submission.files.all().delete()
    Assignment.objects.filter(pk=assignment.pk).update(overdue_processed=False)

    notify_student_credit_retake(assignment.student, assignment)
    messages.success(
        request,
        f"Пересдача открыта для «{assignment.title}». Ученик может начать зачёт заново.",
    )
    return redirect(_student_tab_url(assignment.student_id, "credit"))


def _finalize_expired_credit(assignment, submission):
    """Auto-submit credit when timer is over."""
    if not assignment.is_credit() or submission.submitted_at:
        return False
    if submission.exam_ends_at and timezone.now() >= submission.exam_ends_at:
        submission.submitted_at = timezone.now()
        submission.save(update_fields=["submitted_at"])
        notify_teachers_about_submission(assignment, assignment.student)
        return True
    return False


def _credit_submit_flow(request, assignment, submission):
    locked = bool(submission.submitted_at)

    if locked:
        return render(
            request,
            "classroom/credit_done.html",
            {"assignment": assignment, "submission": submission},
        )

    if assignment.is_exam_in_progress():
        return render(
            request,
            "classroom/credit_exam.html",
            {
                "assignment": assignment,
                "submission": submission,
                "ends_at_iso": submission.exam_ends_at.isoformat(),
                "started_at_iso": submission.exam_started_at.isoformat(),
                "duration_seconds": (assignment.duration_minutes or 0) * 60,
                "remaining_seconds": submission.exam_remaining_seconds(),
                "exam_lock": True,
            },
        )

    # Lobby: description + duration, no teacher files yet
    return render(
        request,
        "classroom/credit_lobby.html",
        {
            "assignment": assignment,
            "submission": submission,
        },
    )


@student_required
@require_POST
def credit_start(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj"),
        pk=assignment_id,
        student=request.user,
        assignment_type=Assignment.AssignmentType.CREDIT,
    )
    if not assignment.is_accessible_to_student():
        messages.error(request, "Зачёт закрыт.")
        return redirect(_student_assignments_url(Assignment.AssignmentType.CREDIT))

    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    _finalize_expired_credit(assignment, submission)
    if submission.submitted_at:
        messages.info(request, "Зачёт уже сдан.")
        return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

    if submission.exam_started_at and assignment.is_exam_in_progress():
        return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

    minutes = assignment.duration_minutes or 60
    now = timezone.now()
    submission.exam_started_at = now
    submission.exam_ends_at = now + timedelta(minutes=minutes)
    submission.save(update_fields=["exam_started_at", "exam_ends_at"])
    messages.success(request, "Зачёт начат. Удачи!")
    return redirect("classroom:assignment_submit", assignment_id=assignment.pk)


@student_required
@require_POST
def credit_autosave(request, assignment_id: int):
    from django.http import JsonResponse

    assignment = get_object_or_404(
        Assignment,
        pk=assignment_id,
        student=request.user,
        assignment_type=Assignment.AssignmentType.CREDIT,
    )
    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    if _finalize_expired_credit(assignment, submission):
        return JsonResponse({"ok": False, "expired": True, "redirect": reverse("classroom:assignment_submit", args=[assignment.pk])})
    if submission.submitted_at or not assignment.is_exam_in_progress():
        return JsonResponse({"ok": False, "error": "exam_not_active"}, status=400)

    submission.text = request.POST.get("text", submission.text)
    submission.save(update_fields=["text"])
    return JsonResponse({"ok": True, "saved_at": timezone.now().isoformat()})


@student_required
@require_POST
def credit_upload(request, assignment_id: int):
    from django.http import JsonResponse

    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj"),
        pk=assignment_id,
        student=request.user,
        assignment_type=Assignment.AssignmentType.CREDIT,
    )
    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    if _finalize_expired_credit(assignment, submission):
        return JsonResponse(
            {
                "ok": False,
                "expired": True,
                "redirect": reverse("classroom:assignment_submit", args=[assignment.pk]),
            }
        )
    if submission.submitted_at or not assignment.is_exam_in_progress():
        return JsonResponse({"ok": False, "error": "exam_not_active"}, status=400)

    files = request.FILES.getlist("files")
    created, errors = _save_uploaded_files(
        files,
        SubmissionFile,
        teacher=_teacher_for_student(request.user),
        submission=submission,
    )
    return JsonResponse(
        {
            "ok": bool(created) or not errors,
            "errors": errors,
            "files": [_submission_file_payload(f) for f in created],
        },
        status=200 if (created or not files) else (200 if created else 400),
    )


@student_required
@require_POST
def credit_finish(request, assignment_id: int):
    assignment = get_object_or_404(
        Assignment.objects.select_related("submission_obj"),
        pk=assignment_id,
        student=request.user,
        assignment_type=Assignment.AssignmentType.CREDIT,
    )
    submission, _ = Submission.objects.get_or_create(assignment=assignment)
    if submission.submitted_at:
        return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

    if not submission.exam_started_at:
        messages.error(request, "Сначала начните зачёт.")
        return redirect("classroom:assignment_submit", assignment_id=assignment.pk)

    text = request.POST.get("text")
    if text is not None:
        submission.text = text
    submission.submitted_at = timezone.now()
    submission.save()
    files = request.FILES.getlist("files")
    if files:
        _, file_errors = _save_uploaded_files(
            files,
            SubmissionFile,
            teacher=_teacher_for_student(request.user),
            submission=submission,
        )
        for err in file_errors:
            messages.error(request, err)
    notify_teachers_about_submission(assignment, request.user)
    messages.success(request, "Зачёт сдан.")
    return redirect(_student_assignments_url(assignment.assignment_type))


@login_required
def notifications_list(request):
    notes = list(request.user.notifications.all()[:50])
    _annotate_notification_actions(notes)
    return render(request, "classroom/notifications.html", {"notifications": notes})


@login_required
def notifications_poll(request):
    """Lightweight poll for unread count and new notification toasts."""
    try:
        since_id = int(request.GET.get("since") or 0)
    except (TypeError, ValueError):
        since_id = 0

    qs = request.user.notifications.all()
    unread = qs.filter(is_read=False).count()
    latest = qs.first()
    latest_id = latest.pk if latest else 0

    items = []
    if since_id > 0:
        for note in qs.filter(pk__gt=since_id).order_by("id")[:8]:
            items.append(
                {
                    "id": note.pk,
                    "title": note.title,
                    "message": (note.message or "")[:160],
                    "link": note.link or reverse("classroom:notifications"),
                    "is_read": note.is_read,
                }
            )

    return JsonResponse(
        {
            "unread": unread,
            "latest_id": latest_id,
            "items": items,
        }
    )


def _annotate_notification_actions(notes):
    """Mark closed-assignment links so UI can show «Задание закрыто» instead of Open."""
    import re

    ids = []
    for note in notes:
        note.action_label = "Открыть"
        note.action_disabled = False
        if not note.link:
            continue
        match = re.search(r"/assignments/(\d+)/submit/?", note.link)
        if match:
            ids.append(int(match.group(1)))

    if not ids:
        return

    closed_ids = set(
        Assignment.objects.filter(pk__in=ids, is_closed=True).values_list("pk", flat=True)
    )
    for note in notes:
        if not note.link:
            continue
        match = re.search(r"/assignments/(\d+)/submit/?", note.link)
        if not match:
            continue
        aid = int(match.group(1))
        if aid in closed_ids:
            note.action_label = "Задание закрыто"
            note.action_disabled = True


@login_required
@require_POST
def notification_mark_read(request, notification_id: int):
    from django.http import HttpResponse

    note = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
    note.is_read = True
    note.save(update_fields=["is_read"])
    stay = request.POST.get("stay") == "1"
    is_htmx = request.headers.get("HX-Request") == "true"

    if not stay and note.link:
        if is_htmx:
            response = HttpResponse(status=204)
            response["HX-Redirect"] = note.link
            return response
        return redirect(note.link)

    if is_htmx:
        notes = [note]
        _annotate_notification_actions(notes)
        unread = request.user.notifications.filter(is_read=False).count()
        return render(
            request,
            "classroom/_notification_read_response.html",
            {"note": notes[0], "unread_notifications": unread},
        )

    return redirect("classroom:notifications")


@login_required
@require_POST
def notifications_mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        notes = list(request.user.notifications.all()[:50])
        _annotate_notification_actions(notes)
        return render(
            request,
            "classroom/_notifications_list_body.html",
            {
                "notifications": notes,
                "unread_notifications": 0,
                "swap_badge": True,
                "swap_heading": True,
            },
        )
    messages.success(request, "Все уведомления прочитаны.")
    return redirect("classroom:notifications")


def _user_can_access_file(user, owner_student):
    profile = getattr(user, "profile", None)
    if profile and profile.is_teacher:
        return _teacher_owns_student(user, owner_student)
    return user.pk == owner_student.pk


def _exam_lock_blocks_file(request, assignment: Assignment | None) -> bool:
    """During an active credit, student may only open that credit's files."""
    active = getattr(request, "active_credit", None)
    if not active:
        return False
    profile = getattr(request.user, "profile", None)
    if not profile or not profile.is_student:
        return False
    if assignment is None or assignment.pk != active.pk:
        return True
    return False


@login_required
def download_material_file(request, file_id: int):
    item = get_object_or_404(MaterialFile.objects.select_related("material"), pk=file_id)
    if not _user_can_access_file(request.user, item.material.student):
        raise Http404()
    if _exam_lock_blocks_file(request, None):
        raise Http404()
    return _file_response(item.file, item.original_name)


@login_required
def download_assignment_file(request, file_id: int):
    item = get_object_or_404(
        AssignmentFile.objects.select_related("assignment"), pk=file_id
    )
    if not _user_can_access_file(request.user, item.assignment.student):
        raise Http404()
    if _exam_lock_blocks_file(request, item.assignment):
        raise Http404()
    return _file_response(item.file, item.original_name)


@login_required
def download_submission_file(request, file_id: int):
    item = get_object_or_404(
        SubmissionFile.objects.select_related("submission__assignment"), pk=file_id
    )
    if not _user_can_access_file(request.user, item.submission.assignment.student):
        raise Http404()
    if _exam_lock_blocks_file(request, item.submission.assignment):
        raise Http404()
    return _file_response(item.file, item.original_name)


def _file_response(field_file, download_name: str = ""):
    if not field_file:
        raise Http404()
    try:
        field_file.open("rb")
    except FileNotFoundError as exc:
        raise Http404() from exc
    name = download_name or Path(field_file.name).name
    return FileResponse(field_file, as_attachment=False, filename=name)
