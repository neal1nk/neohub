"""Per-teacher storage quota: teacher files + files of their students."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import QuerySet

from .models import AssignmentFile, MaterialFile, SubmissionFile

TEACHER_STORAGE_LIMIT_BYTES = 400 * 1024 * 1024  # 400 MB


def file_field_size(field_file) -> int:
    if not field_file:
        return 0
    try:
        size = field_file.size
        return int(size) if size is not None else 0
    except Exception:
        return 0


def _sum_queryset_files(qs: QuerySet) -> int:
    total = 0
    for item in qs.only("file").iterator():
        total += file_field_size(item.file)
    return total


def teacher_storage_used_bytes(teacher: User) -> int:
    """Bytes used by materials/assignments for teacher's students + their submissions."""
    total = 0
    total += _sum_queryset_files(
        MaterialFile.objects.filter(material__student__profile__teacher=teacher)
    )
    total += _sum_queryset_files(
        AssignmentFile.objects.filter(assignment__student__profile__teacher=teacher)
    )
    total += _sum_queryset_files(
        SubmissionFile.objects.filter(
            submission__assignment__student__profile__teacher=teacher
        )
    )
    return total


def format_mb(num_bytes: int | float) -> str:
    mb = float(num_bytes) / (1024 * 1024)
    if mb < 10:
        return f"{mb:.1f}".rstrip("0").rstrip(".")
    return f"{mb:.0f}"


def teacher_storage_stats(teacher: User) -> dict:
    used = teacher_storage_used_bytes(teacher)
    limit = TEACHER_STORAGE_LIMIT_BYTES
    percent = 0.0 if limit <= 0 else min(100.0, (used / limit) * 100.0)
    remaining = max(0, limit - used)
    return {
        "used_bytes": used,
        "limit_bytes": limit,
        "used_mb": used / (1024 * 1024),
        "limit_mb": limit // (1024 * 1024),
        "used_label": format_mb(used),
        "limit_label": str(limit // (1024 * 1024)),
        "percent": round(percent, 1),
        "remaining_bytes": remaining,
        "is_warning": percent >= 80,
        "is_critical": percent >= 95,
        "is_full": remaining <= 0,
    }


def incoming_upload_bytes(files) -> int:
    total = 0
    for uploaded in files or []:
        if not uploaded:
            continue
        size = getattr(uploaded, "size", None)
        if size is not None:
            total += int(size)
    return total


def check_teacher_storage_quota(teacher: User | None, files, *, copies: int = 1) -> str:
    """
    Return an error message if uploads would exceed quota, else empty string.
    `copies` — how many times the same files are stored (bulk assign to N students).
    """
    if teacher is None:
        return ""
    incoming = incoming_upload_bytes(files) * max(1, copies)
    if incoming <= 0:
        return ""
    used = teacher_storage_used_bytes(teacher)
    if used + incoming <= TEACHER_STORAGE_LIMIT_BYTES:
        return ""
    limit_mb = TEACHER_STORAGE_LIMIT_BYTES // (1024 * 1024)
    return (
        f"Недостаточно места в хранилище. Лимит {limit_mb} МБ "
        f"(занято {format_mb(used)} МБ, нужно ещё {format_mb(incoming)} МБ)."
    )
