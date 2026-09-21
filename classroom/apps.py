from django.apps import AppConfig


class ClassroomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "classroom"

    def ready(self):
        # noqa: F401 — register signal handlers if added later
        pass
