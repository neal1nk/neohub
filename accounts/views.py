from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.decorators.http import require_http_methods

from .decorators import redirect_by_role, teacher_required
from .forms import (
    ActivationCodeForm,
    CreateTeacherForm,
    LoginForm,
    PersonalDataForm,
)
from .models import ActivationCode

TEACHER_ACTIVATION_SESSION_KEY = "neohub_teacher_activation_ok"


class GhubLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("accounts:dashboard")


class GhubLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")


class DashboardRedirectView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        return redirect_by_role(request.user)


@teacher_required
@require_http_methods(["GET", "POST"])
def teacher_profile(request):
    form = PersonalDataForm(
        request.POST if request.method == "POST" else None,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профиль обновлён.")
        return redirect("accounts:teacher_profile")
    return render(request, "accounts/teacher_profile.html", {"form": form})


@require_http_methods(["GET", "POST"])
def access_activate(request):
    """Enter activation code to unlock teacher registration."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = ActivationCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ok, error, code_obj = ActivationCode.find_valid(form.cleaned_data["code"])
        if not ok:
            form.add_error("code", error)
        else:
            request.session[TEACHER_ACTIVATION_SESSION_KEY] = True
            request.session["neohub_activation_code_id"] = code_obj.pk
            messages.success(
                request, "Код принят. Создайте аккаунт преподавателя."
            )
            return redirect("accounts:teacher_register")

    return render(request, "accounts/access_activate.html", {"form": form})


@require_http_methods(["GET", "POST"])
def teacher_register(request):
    """Create teacher account after successful activation."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    if not request.session.get(TEACHER_ACTIVATION_SESSION_KEY):
        messages.error(request, "Сначала введите код активации.")
        return redirect("accounts:access_activate")

    code_id = request.session.get("neohub_activation_code_id")
    code_obj = ActivationCode.objects.filter(pk=code_id, is_used=False, is_active=True).first()
    if not code_obj:
        request.session.pop(TEACHER_ACTIVATION_SESSION_KEY, None)
        request.session.pop("neohub_activation_code_id", None)
        messages.error(request, "Код активации больше недействителен.")
        return redirect("accounts:access_activate")

    form = CreateTeacherForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        code_obj.mark_used(user)
        request.session.pop("neohub_activation_code_id", None)
        request.session.pop(TEACHER_ACTIVATION_SESSION_KEY, None)
        login(request, user)
        messages.success(request, "Аккаунт преподавателя создан.")
        return redirect("classroom:teacher_dashboard")

    return render(request, "accounts/teacher_register.html", {"form": form})
