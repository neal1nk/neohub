from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.DashboardRedirectView.as_view(), name="dashboard"),
    path("login/", views.GhubLoginView.as_view(), name="login"),
    path("logout/", views.GhubLogoutView.as_view(), name="logout"),
    path("profile/", views.teacher_profile, name="teacher_profile"),
    path("access/", views.access_activate, name="access_activate"),
    path("access/register/", views.teacher_register, name="teacher_register"),
]
