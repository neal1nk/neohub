from django.conf import settings
from django.db import models
from django.db.models import Avg
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    class Role(models.TextChoices):
        TEACHER = "teacher", "Преподаватель"
        STUDENT = "student", "Ученик"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    display_name = models.CharField(max_length=150, blank=True)
    telegram = models.CharField(max_length=100, blank=True)
    whatsapp = models.CharField(max_length=100, blank=True)
    max_messenger = models.CharField("MAX", max_length=100, blank=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="owned_students",
        limit_choices_to={"profile__role": "teacher"},
        help_text="Преподаватель, которому принадлежит ученик.",
    )

    class Meta:
        ordering = ["display_name", "user__username"]

    def __str__(self) -> str:
        return f"{self.get_display_name()} ({self.get_role_display()})"

    def get_display_name(self) -> str:
        if self.display_name:
            return self.display_name
        full = self.user.get_full_name().strip()
        return full or self.user.username

    @property
    def is_teacher(self) -> bool:
        return self.role == self.Role.TEACHER

    @property
    def is_student(self) -> bool:
        return self.role == self.Role.STUDENT

    def rating_score(self) -> int | None:
        if not self.is_student:
            return None
        avg = self.user.assignments.filter(
            is_for_grade=True,
            submission_obj__grade__isnull=False,
        ).aggregate(avg=Avg("submission_obj__grade"))["avg"]
        if avg is None:
            return None
        return int(round(avg))

    def rating_breakdown(self) -> dict:
        """Counts of graded-for-score works by type."""
        from classroom.models import Assignment

        if not self.is_student:
            return {"homework": 0, "practice": 0, "credit": 0, "total": 0}
        qs = self.user.assignments.filter(
            is_for_grade=True,
            submission_obj__grade__isnull=False,
        )
        homework = qs.filter(assignment_type=Assignment.AssignmentType.HOMEWORK).count()
        practice = qs.filter(assignment_type=Assignment.AssignmentType.PRACTICE).count()
        credit = qs.filter(assignment_type=Assignment.AssignmentType.CREDIT).count()
        return {
            "homework": homework,
            "practice": practice,
            "credit": credit,
            "total": homework + practice + credit,
        }

    def rating_breakdown_text(self) -> str:
        data = self.rating_breakdown()
        if data["total"] == 0:
            return "Пока нет оценённых работ в рейтинге."

        def _ru(n: int, one: str, few: str, many: str) -> str:
            n_abs = abs(n) % 100
            n1 = n_abs % 10
            if 11 <= n_abs <= 19:
                word = many
            elif n1 == 1:
                word = one
            elif 2 <= n1 <= 4:
                word = few
            else:
                word = many
            return f"{n} {word}"

        parts = []
        if data["homework"]:
            parts.append(_ru(data["homework"], "домашке", "домашкам", "домашкам"))
        if data["practice"]:
            parts.append(_ru(data["practice"], "практике", "практикам", "практикам"))
        if data["credit"]:
            parts.append(_ru(data["credit"], "зачёту", "зачётам", "зачётам"))
        if len(parts) == 1:
            joined = parts[0]
        elif len(parts) == 2:
            joined = f"{parts[0]} и {parts[1]}"
        else:
            joined = f"{parts[0]}, {parts[1]} и {parts[2]}"
        return f"Средний балл по {joined}."

    def rating_color(self) -> str:
        score = self.rating_score()
        if score is None:
            return "#666666"
        # 0 = red, 100 = green
        red = int(220 - (score * 1.6))
        green = int(60 + (score * 1.6))
        blue = 70
        return f"rgb({red}, {green}, {blue})"

    def study_stats(self) -> dict:
        """Aggregate learning stats for teacher/student dashboards."""
        from django.utils import timezone

        from classroom.models import Assignment

        if not self.is_student:
            return {
                "average": None,
                "total": 0,
                "submitted": 0,
                "graded": 0,
                "overdue": 0,
                "open": 0,
                "recent_grades": [],
            }

        assignments = list(
            self.user.assignments.select_related("submission_obj").all()
        )
        now = timezone.now()
        submitted = 0
        graded = 0
        overdue = 0
        open_count = 0
        grade_points: list[tuple] = []

        for a in assignments:
            sub = a.submission
            status = a.compute_status()
            if sub and sub.submitted_at:
                submitted += 1
            if status == Assignment.Status.GRADED:
                graded += 1
            if status == Assignment.Status.OVERDUE or (
                a.show_overdue_badge() and not (sub and sub.submitted_at)
            ):
                overdue += 1
            if status in (Assignment.Status.OPEN, Assignment.Status.OVERDUE) and not a.is_closed:
                open_count += 1
            if a.is_for_grade and sub and sub.grade is not None:
                when = sub.graded_at or sub.submitted_at or a.updated_at
                grade_points.append((when, sub.grade, a.title, a.type_badge_label()))

        grade_points.sort(key=lambda x: x[0] or now)
        recent = grade_points[-8:]
        average = self.rating_score()
        return {
            "average": average,
            "total": len(assignments),
            "submitted": submitted,
            "graded": graded,
            "overdue": overdue,
            "open": open_count,
            "recent_grades": [
                {
                    "grade": g,
                    "title": title,
                    "type": typ,
                    "date": when,
                }
                for when, g, title, typ in recent
            ],
        }


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created or not Profile.objects.filter(user=instance).exists():
        role = Profile.Role.TEACHER if instance.is_superuser else Profile.Role.STUDENT
        Profile.objects.get_or_create(
            user=instance,
            defaults={
                "role": role,
                "display_name": instance.get_full_name() or instance.username,
            },
        )


class ActivationCode(models.Model):
    """One-time (or reusable) codes to unlock teacher registration."""

    code = models.CharField(max_length=19, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="used_activation_codes",
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status = "использован" if self.is_used else ("активен" if self.is_active else "выключен")
        return f"{self.code} ({status})"

    @staticmethod
    def normalize(raw: str) -> str:
        cleaned = "".join(ch for ch in (raw or "").upper() if ch.isalnum())
        if len(cleaned) != 16:
            return ""
        return "-".join(
            [cleaned[0:4], cleaned[4:8], cleaned[8:12], cleaned[12:16]]
        )

    @classmethod
    def find_valid(cls, raw: str):
        """Validate code without consuming. Returns (ok, error_message, instance)."""
        normalized = cls.normalize(raw)
        if not normalized:
            return False, "Код должен быть в формате XXXX-XXXX-XXXX-XXXX.", None
        try:
            item = cls.objects.get(code=normalized)
        except cls.DoesNotExist:
            return False, "Неверный код активации.", None
        if not item.is_active:
            return False, "Этот код отключён.", None
        if item.is_used:
            return False, "Этот код уже использован.", None
        return True, "", item

    def mark_used(self, user=None):
        from django.utils import timezone

        self.is_used = True
        self.used_at = timezone.now()
        if user is not None:
            self.used_by = user
        self.save(update_fields=["is_used", "used_at", "used_by"])
