from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django import forms

from .models import Profile


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Логин",
        widget=forms.TextInput(
            attrs={"class": "input", "placeholder": "Логин", "autocomplete": "username"}
        ),
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": "Пароль",
                "autocomplete": "current-password",
            }
        ),
    )


class CreateStudentForm(forms.Form):
    display_name = forms.CharField(
        label="ФИО",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Иван Иванов"}),
    )
    username = forms.CharField(
        label="Логин",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "ivanov"}),
    )
    password = forms.CharField(
        label="Пароль",
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Минимум 6 символов",
                "autocomplete": "new-password",
                "spellcheck": "false",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Повтор пароля",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Повтор пароля",
                "autocomplete": "new-password",
                "spellcheck": "false",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Такой логин уже занят.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error("password_confirm", "Пароли не совпадают.")
        return cleaned

    def save(self, teacher=None):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password"],
        )
        profile = user.profile
        profile.role = Profile.Role.STUDENT
        profile.display_name = self.cleaned_data["display_name"]
        if teacher is not None:
            profile.teacher = teacher
        profile.save()
        return user


class PersonalDataForm(forms.Form):
    display_name = forms.CharField(
        label="ФИО",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    username = forms.CharField(
        label="Логин",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    password = forms.CharField(
        label="Новый пароль",
        required=False,
        min_length=6,
        widget=forms.PasswordInput(
            attrs={"class": "input", "placeholder": "Оставьте пустым, чтобы не менять"}
        ),
    )
    password_confirm = forms.CharField(
        label="Повтор пароля",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "input"}),
    )
    email = forms.EmailField(
        label="Почта",
        required=False,
        widget=forms.EmailInput(attrs={"class": "input", "placeholder": "name@example.com"}),
    )
    telegram = forms.CharField(
        label="Telegram",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "@username"}),
    )
    whatsapp = forms.CharField(
        label="WhatsApp",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "+7..."}),
    )
    max_messenger = forms.CharField(
        label="MAX",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Ник или телефон"}),
    )

    def __init__(self, *args, user: User, **kwargs):
        self.target_user = user
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            profile = user.profile
            initials = {
                "display_name": profile.display_name or user.get_full_name() or user.username,
                "username": user.username,
                "email": user.email or "",
                "telegram": profile.telegram or "",
                "whatsapp": profile.whatsapp or "",
                "max_messenger": profile.max_messenger or "",
            }
            self.initial.update(initials)
            for name, value in initials.items():
                self.fields[name].initial = value

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        qs = User.objects.filter(username__iexact=username).exclude(pk=self.target_user.pk)
        if qs.exists():
            raise forms.ValidationError("Такой логин уже занят.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password or confirm:
            if password != confirm:
                self.add_error("password_confirm", "Пароли не совпадают.")
        return cleaned

    def save(self):
        user = self.target_user
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data.get("email") or ""
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        user.save()

        profile = user.profile
        profile.display_name = self.cleaned_data["display_name"]
        profile.telegram = self.cleaned_data.get("telegram") or ""
        profile.whatsapp = self.cleaned_data.get("whatsapp") or ""
        profile.max_messenger = self.cleaned_data.get("max_messenger") or ""
        profile.save()
        return user


# Backward-compatible alias
class StudentPersonalDataForm(PersonalDataForm):
    def __init__(self, *args, student: User | None = None, user: User | None = None, **kwargs):
        target = student or user
        super().__init__(*args, user=target, **kwargs)


class ActivationCodeForm(forms.Form):
    code = forms.CharField(
        label="Код активации",
        max_length=19,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "XXXX-XXXX-XXXX-XXXX",
                "autocomplete": "off",
                "spellcheck": "false",
                "inputmode": "text",
                "maxlength": "19",
            }
        ),
    )

    def clean_code(self):
        from .models import ActivationCode

        raw = self.cleaned_data["code"]
        normalized = ActivationCode.normalize(raw)
        if not normalized:
            raise forms.ValidationError(
                "Введите код в формате XXXX-XXXX-XXXX-XXXX."
            )
        return normalized


class CreateTeacherForm(forms.Form):
    display_name = forms.CharField(
        label="ФИО",
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "input", "placeholder": "Иван Иванов"}
        ),
    )
    username = forms.CharField(
        label="Логин",
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "input", "placeholder": "teacher", "autocomplete": "username"}
        ),
    )
    password = forms.CharField(
        label="Пароль",
        min_length=6,
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": "Минимум 6 символов",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Повтор пароля",
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": "Повтор пароля",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Такой логин уже занят.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error("password_confirm", "Пароли не совпадают.")
        return cleaned

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password"],
        )
        profile = user.profile
        profile.role = Profile.Role.TEACHER
        profile.display_name = self.cleaned_data["display_name"]
        profile.save()
        return user
