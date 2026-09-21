"""Upload validation shared by views and UI hints."""

from pathlib import Path

from django.core.exceptions import ValidationError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = frozenset(
    {
        # images
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "bmp",
        # documents
        "pdf",
        "doc",
        "docx",
        "txt",
        "rtf",
        "odt",
        "xls",
        "xlsx",
        "csv",
        "ppt",
        "pptx",
    }
)

ACCEPT_ATTR = (
    ".jpg,.jpeg,.png,.gif,.webp,.bmp,"
    ".pdf,.doc,.docx,.txt,.rtf,.odt,"
    ".xls,.xlsx,.csv,.ppt,.pptx"
)

UPLOAD_HINT = (
    "Фото и документы: PDF, DOC/DOCX, TXT и др. · до 10 МБ каждый · файлы добавляются, не заменяются"
)


def file_extension(name: str) -> str:
    return Path(name or "").suffix.lower().lstrip(".")


def validate_uploaded_file(uploaded) -> None:
    name = getattr(uploaded, "name", "") or ""
    ext = file_extension(name)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Файл «{name}»: разрешены только изображения и документы "
            f"(pdf, docx, txt, jpg…)."
        )
    size = getattr(uploaded, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(f"Файл «{name}» больше {mb} МБ.")


def filter_valid_uploads(files) -> tuple[list, list[str]]:
    """Return (accepted_files, error_messages)."""
    ok = []
    errors = []
    for uploaded in files or []:
        if not uploaded:
            continue
        try:
            validate_uploaded_file(uploaded)
            ok.append(uploaded)
        except ValidationError as exc:
            errors.extend(exc.messages)
    return ok, errors
