from django import forms
from django.utils import timezone

from .models import Assignment, Material, Submission


class NeoHubDateTimeInput(forms.TextInput):
    """Text field that stores YYYY-MM-DDTHH:MM and opens NeoHub picker via JS."""

    def __init__(self, attrs=None):
        base = {
            "class": "input neohub-datetime",
            "placeholder": "Выберите дату и время",
            "autocomplete": "off",
            "inputmode": "none",
            "readonly": "readonly",
        }
        if attrs:
            base.update(attrs)
            if "class" in attrs and "neohub-datetime" not in attrs["class"]:
                base["class"] = f"{attrs['class']} neohub-datetime".strip()
        super().__init__(attrs=base)

    def format_value(self, value):
        if value is None or value == "":
            return ""
        if hasattr(value, "strftime"):
            local = timezone.localtime(value) if timezone.is_aware(value) else value
            return local.strftime("%Y-%m-%dT%H:%M")
        return str(value)


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ["title", "body", "link"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Название материала"}),
            "body": forms.Textarea(
                attrs={
                    "class": "input textarea",
                    "rows": 6,
                    "placeholder": "Текст теории...",
                }
            ),
            "link": forms.URLInput(
                attrs={"class": "input", "placeholder": "https://... (необязательно)"}
            ),
        }
        labels = {
            "title": "Название",
            "body": "Текст",
            "link": "Ссылка",
        }


class AssignmentForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        label="Дедлайн (необязательно)",
        required=False,
        widget=NeoHubDateTimeInput(),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
    )
    is_closed = forms.BooleanField(
        label="Закрыть для ученика",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "lock-toggle-input"}),
    )
    unlock_at = forms.DateTimeField(
        label="Автооткрытие (если закрыто)",
        required=False,
        widget=NeoHubDateTimeInput(),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
    )
    duration_minutes = forms.IntegerField(
        label="Время на выполнение (минуты)",
        required=False,
        min_value=1,
        max_value=24 * 60,
        widget=forms.NumberInput(
            attrs={"class": "input", "placeholder": "Например, 90", "min": 1}
        ),
    )

    class Meta:
        model = Assignment
        fields = [
            "title",
            "description",
            "instruction",
            "duration_minutes",
            "deadline",
            "is_closed",
            "unlock_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Название задания"}),
            "description": forms.Textarea(
                attrs={
                    "class": "input textarea",
                    "rows": 4,
                    "placeholder": "Описание задания…",
                }
            ),
            "instruction": forms.Textarea(
                attrs={
                    "class": "input textarea",
                    "rows": 5,
                    "placeholder": "Инструкция (видна после начала зачёта)…",
                }
            ),
        }
        labels = {
            "title": "Название",
            "description": "Описание",
            "instruction": "Инструкция",
        }

    def __init__(self, *args, assignment_type: str | None = None, **kwargs):
        self.assignment_type = assignment_type
        super().__init__(*args, **kwargs)
        is_credit = assignment_type == Assignment.AssignmentType.CREDIT
        if not is_credit:
            self.fields.pop("instruction", None)
            self.fields.pop("duration_minutes", None)
            if "description" in self.fields:
                self.fields["description"].label = "Описание"
                self.fields["description"].widget.attrs["placeholder"] = (
                    "Описание задания…"
                )
        else:
            self.fields["duration_minutes"].required = True
            self.fields["description"].label = "Описание (до начала)"
            self.fields["description"].widget.attrs["placeholder"] = (
                "Краткое описание (видно до начала зачёта)…"
            )
            self.fields["instruction"].required = False
            self.fields["instruction"].widget.attrs["placeholder"] = (
                "Инструкция (видна после начала зачёта)…"
            )
    def clean_deadline(self):
        deadline = self.cleaned_data.get("deadline")
        if deadline and deadline < timezone.now() and not self.instance.pk:
            raise forms.ValidationError("Дедлайн не может быть в прошлом.")
        return deadline

    def clean(self):
        cleaned = super().clean()
        is_closed = cleaned.get("is_closed")
        unlock_at = cleaned.get("unlock_at")
        if unlock_at and not is_closed:
            cleaned["is_closed"] = True
        if unlock_at and unlock_at < timezone.now() and not self.instance.pk:
            self.add_error("unlock_at", "Дата автооткрытия не может быть в прошлом.")
        if self.assignment_type == Assignment.AssignmentType.CREDIT:
            if not cleaned.get("duration_minutes"):
                self.add_error("duration_minutes", "Укажите время на выполнение зачёта.")
        return cleaned


class GradeFeedbackForm(forms.Form):
    student_comment = forms.CharField(
        label="Вопрос к оценке",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "input textarea",
                "rows": 3,
                "placeholder": "Что непонятно в оценке? (необязательно)",
            }
        ),
    )

    def clean_student_comment(self):
        text = (self.cleaned_data.get("student_comment") or "").strip()
        return text or "Прошу пояснить оценку."


class GradeClarifyForm(forms.Form):
    clarification = forms.CharField(
        label="Пояснение",
        widget=forms.Textarea(
            attrs={
                "class": "input textarea",
                "rows": 3,
                "placeholder": "Поясните оценку ученику…",
            }
        ),
    )

    def clean_clarification(self):
        text = (self.cleaned_data.get("clarification") or "").strip()
        if not text:
            raise forms.ValidationError("Напишите пояснение.")
        return text


class ExtendDeadlineForm(forms.Form):
    deadline = forms.DateTimeField(
        label="Новый дедлайн",
        widget=NeoHubDateTimeInput(),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
    )

    def __init__(self, *args, current_deadline=None, **kwargs):
        self.current_deadline = current_deadline
        super().__init__(*args, **kwargs)

    def clean_deadline(self):
        deadline = self.cleaned_data.get("deadline")
        if not deadline:
            raise forms.ValidationError("Выберите новый дедлайн.")
        if timezone.is_naive(deadline):
            deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
        if deadline <= timezone.now():
            raise forms.ValidationError("Новый дедлайн должен быть в будущем.")
        if self.current_deadline and deadline <= self.current_deadline:
            raise forms.ValidationError(
                "Новый дедлайн должен быть позже текущего."
            )
        return deadline


class SubmissionForm(forms.Form):
    text = forms.CharField(
        label="Ответ",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "input textarea",
                "rows": 5,
                "placeholder": "Ваш ответ...",
            }
        ),
    )

    def __init__(self, *args, has_files=False, **kwargs):
        self.has_files = has_files
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("text") and not self.has_files:
            raise forms.ValidationError("Добавьте текст ответа или файл.")
        return cleaned


class GradeForm(forms.ModelForm):
    grade = forms.IntegerField(
        label="Баллы (0–100)",
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(
            attrs={
                "class": "input score-input",
                "type": "range",
                "min": 0,
                "max": 100,
                "step": 1,
            }
        ),
    )

    class Meta:
        model = Submission
        fields = ["grade", "teacher_comment"]
        widgets = {
            "teacher_comment": forms.Textarea(
                attrs={
                    "class": "input textarea",
                    "rows": 3,
                    "placeholder": "Комментарий ученику...",
                }
            ),
        }
        labels = {
            "teacher_comment": "Комментарий",
        }


class FormalGradeForm(forms.ModelForm):
    formal_grade = forms.ChoiceField(
        label="Формальная оценка",
        choices=Submission.FormalGrade.choices,
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = Submission
        fields = ["formal_grade", "teacher_comment"]
        widgets = {
            "teacher_comment": forms.Textarea(
                attrs={
                    "class": "input textarea",
                    "rows": 3,
                    "placeholder": "Комментарий ученику...",
                }
            ),
        }
        labels = {
            "teacher_comment": "Комментарий",
        }
