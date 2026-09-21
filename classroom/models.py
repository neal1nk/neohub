from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Material(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="materials",
        limit_choices_to={"profile__role": "student"},
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.URLField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_materials",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class MaterialFile(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="materials/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.original_name or self.file.name


class Assignment(models.Model):
    class AssignmentType(models.TextChoices):
        HOMEWORK = "homework", "Домашнее задание"
        PRACTICE = "practice", "Практика"
        CREDIT = "credit", "Зачёт"

    class Status(models.TextChoices):
        OPEN = "open", "Открыто"
        SUBMITTED = "submitted", "Сдано"
        GRADED = "graded", "Оценено"
        OVERDUE = "overdue", "Просрочено"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assignments",
        limit_choices_to={"profile__role": "student"},
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.HOMEWORK,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instruction = models.TextField(
        "Инструкция",
        blank=True,
        help_text="Подробная инструкция для зачёта (видна после начала).",
    )
    duration_minutes = models.PositiveIntegerField(
        "Время на зачёт (мин)",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(24 * 60)],
        help_text="Обязательно для зачёта.",
    )
    deadline = models.DateTimeField(null=True, blank=True)
    is_for_grade = models.BooleanField(
        "На оценку",
        default=True,
        help_text="Если выключено, задание не влияет на рейтинг и не оценивается.",
    )
    is_closed = models.BooleanField(
        "Закрыто для ученика",
        default=False,
        help_text="Закрытое задание нельзя открыть, пока преподаватель не откроет или не сработает автооткрытие.",
    )
    unlock_at = models.DateTimeField(
        "Автооткрытие",
        null=True,
        blank=True,
        help_text="Если задание закрыто, оно откроется автоматически в это время.",
    )
    overdue_processed = models.BooleanField(
        "Просрочка обработана",
        default=False,
        help_text="Служебное: автооценка 0 и уведомления о просрочке уже выставлены.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_assignment_type_display()}: {self.title}"

    @property
    def submission(self):
        return getattr(self, "submission_obj", None)

    def compute_status(self) -> str:
        submission = self.submission
        if submission and submission.is_graded:
            return self.Status.GRADED
        if submission and submission.is_submitted:
            return self.Status.SUBMITTED
        if self.deadline and self.deadline < timezone.now():
            return self.Status.OVERDUE
        return self.Status.OPEN

    def status_label(self) -> str:
        status = self.compute_status()
        # Deadline overdue is always visible on the card
        if status == self.Status.OVERDUE:
            return "Просрочено"
        if self.is_closed and status != self.Status.GRADED:
            return "Закрыто"
        return dict(self.Status.choices).get(status, status)

    def is_past_deadline(self) -> bool:
        return bool(self.deadline and self.deadline < timezone.now())

    def is_submitted(self) -> bool:
        submission = self.submission
        return bool(submission and submission.submitted_at)

    def should_show_deadline_countdown(self) -> bool:
        """Countdown only while work is still open (not submitted/graded)."""
        if not self.deadline:
            return False
        submission = self.submission
        if submission and (submission.submitted_at or submission.is_graded):
            return False
        return True

    def show_overdue_badge(self) -> bool:
        """True when deadline passed and work was not submitted on time (or auto-zeroed)."""
        if self.is_submitted():
            return False
        if not self.is_past_deadline():
            return False
        if self.compute_status() == self.Status.OVERDUE:
            return True
        if self.overdue_processed:
            return True
        return False

    def grade_note(self) -> str:
        """Short explanation for recent grades (deadline / pass-fail / formal)."""
        submission = self.submission
        if not submission or not submission.is_graded:
            return ""
        comment = (submission.teacher_comment or "").lower()
        if "дедлайн" in comment or (
            self.overdue_processed and submission.grade == 0
        ):
            return "Дедлайн истёк"
        credit = self.credit_result_label()
        if credit:
            return credit
        if not self.is_for_grade and submission.formal_grade:
            return submission.get_formal_grade_display()
        return ""

    def type_badge_label(self) -> str:
        return {
            self.AssignmentType.HOMEWORK: "Домашка",
            self.AssignmentType.PRACTICE: "Практика",
            self.AssignmentType.CREDIT: "Зачетная работа",
        }.get(self.assignment_type, self.get_assignment_type_display())

    def is_accessible_to_student(self) -> bool:
        """Whether the student may open this assignment page."""
        return not self.is_closed

    def is_credit(self) -> bool:
        return self.assignment_type == self.AssignmentType.CREDIT

    def is_locked_for_student(self) -> bool:
        """Cannot edit after final submit (homework/practice/credit)."""
        submission = self.submission
        return bool(submission and submission.submitted_at)

    def is_exam_in_progress(self) -> bool:
        if not self.is_credit():
            return False
        submission = self.submission
        if not submission or submission.submitted_at:
            return False
        if not submission.exam_started_at or not submission.exam_ends_at:
            return False
        return timezone.now() < submission.exam_ends_at

    def is_exam_expired_unsubmitted(self) -> bool:
        if not self.is_credit():
            return False
        submission = self.submission
        if not submission or submission.submitted_at:
            return False
        if not submission.exam_ends_at:
            return False
        return timezone.now() >= submission.exam_ends_at

    def score_color(self) -> str:
        submission = self.submission
        if not submission:
            return "#555555"
        if not self.is_for_grade:
            return self.formal_grade_color()
        if submission.grade is None:
            return "#555555"
        score = submission.grade
        if self.is_credit():
            return "#3dba6e" if score >= 50 else "#d95454"
        red = int(220 - (score * 1.6))
        green = int(60 + (score * 1.6))
        return f"rgb({red}, {green}, 70)"

    def formal_grade_color(self) -> str:
        """Red → green scale for formal (non-score) grades."""
        submission = self.submission
        if not submission or not submission.formal_grade:
            return "#555555"
        return {
            Submission.FormalGrade.POOR: "#d95454",
            Submission.FormalGrade.SATISFACTORY: "#d4a017",
            Submission.FormalGrade.GOOD: "#7cb342",
            Submission.FormalGrade.EXCELLENT: "#3dba6e",
        }.get(submission.formal_grade, "#555555")

    def formal_grade_level(self) -> int:
        """0–100 proxy for formal grade (for fill bars)."""
        submission = self.submission
        if not submission or not submission.formal_grade:
            return 0
        return {
            Submission.FormalGrade.POOR: 25,
            Submission.FormalGrade.SATISFACTORY: 50,
            Submission.FormalGrade.GOOD: 75,
            Submission.FormalGrade.EXCELLENT: 100,
        }.get(submission.formal_grade, 0)

    def credit_result_label(self) -> str | None:
        """Pass/fail label for graded credit assignments."""
        if not self.is_credit():
            return None
        submission = self.submission
        if not submission or submission.grade is None:
            return None
        return "Зачёт" if submission.grade >= 50 else "Не зачёт"

    def credit_badge_modifier(self) -> str:
        """CSS modifier for credit type badge: pass / fail / empty."""
        label = self.credit_result_label()
        if label == "Зачёт":
            return "is-pass"
        if label == "Не зачёт":
            return "is-fail"
        return ""


class AssignmentFile(models.Model):
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="files"
    )
    file = models.FileField(upload_to="assignments/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.original_name or self.file.name


class Submission(models.Model):
    class FormalGrade(models.TextChoices):
        POOR = "poor", "Плохо"
        SATISFACTORY = "satisfactory", "Удовлетворительно"
        GOOD = "good", "Хорошо"
        EXCELLENT = "excellent", "Отлично"

    assignment = models.OneToOneField(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submission_obj",
    )
    text = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    exam_started_at = models.DateTimeField(null=True, blank=True)
    exam_ends_at = models.DateTimeField(null=True, blank=True)
    grade = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    formal_grade = models.CharField(
        max_length=20,
        choices=FormalGrade.choices,
        blank=True,
        help_text="Формальная оценка для заданий без баллов.",
    )
    teacher_comment = models.TextField(blank=True)
    student_comment = models.TextField(
        "Комментарий ученика к оценке",
        blank=True,
    )
    clarification_requested = models.BooleanField(
        "Запрошено пояснение оценки",
        default=False,
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"Сдача: {self.assignment.title}"

    @property
    def is_graded(self) -> bool:
        if self.assignment.is_for_grade:
            return self.grade is not None
        return bool(self.formal_grade)

    @property
    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    def exam_remaining_seconds(self) -> int:
        if not self.exam_ends_at:
            return 0
        delta = self.exam_ends_at - timezone.now()
        return max(0, int(delta.total_seconds()))

    def display_grade(self) -> str:
        if self.assignment.is_credit() and self.assignment.is_for_grade:
            if self.grade is None:
                return "—"
            result = "Зачёт" if self.grade >= 50 else "Не зачёт"
            return f"{self.grade}/100 · {result}"
        if self.assignment.is_for_grade:
            if self.grade is None:
                return "—"
            return f"{self.grade}/100"
        if self.formal_grade:
            return self.get_formal_grade_display()
        return "—"


class SubmissionFile(models.Model):
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="files"
    )
    file = models.FileField(upload_to="submissions/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.original_name or self.file.name


class Notification(models.Model):
    class Kind(models.TextChoices):
        SUBMISSION = "submission", "Сдача работы"
        MATERIAL = "material", "Новая теория"
        ASSIGNMENT = "assignment", "Новое задание"
        ASSIGNMENT_OPEN = "assignment_open", "Открытие задания"
        OVERDUE = "overdue", "Просрочка"
        GRADE = "grade", "Оценка"
        GRADE_QUESTION = "grade_question", "Вопрос по оценке"
        RETAKE = "retake", "Пересдача"
        OTHER = "other", "Другое"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
