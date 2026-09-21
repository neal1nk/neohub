import secrets
import string

from django.core.management.base import BaseCommand

from accounts.models import ActivationCode


def _generate_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    raw = "".join(secrets.choice(alphabet) for _ in range(16))
    return ActivationCode.normalize(raw)


class Command(BaseCommand):
    help = "Create a teacher activation code (XXXX-XXXX-XXXX-XXXX)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--code",
            default="",
            help="Optional fixed code. Random if omitted.",
        )
        parser.add_argument(
            "--note",
            default="",
            help="Optional note for admin.",
        )

    def handle(self, *args, **options):
        raw = (options.get("code") or "").strip()
        code = ActivationCode.normalize(raw) if raw else _generate_code()
        if not code:
            self.stderr.write(self.style.ERROR("Неверный формат кода."))
            return
        obj, created = ActivationCode.objects.get_or_create(
            code=code,
            defaults={"note": options.get("note") or ""},
        )
        if not created:
            if obj.is_used:
                obj.is_used = False
                obj.used_at = None
                obj.used_by = None
                obj.is_active = True
                obj.note = options.get("note") or obj.note
                obj.save()
                self.stdout.write(
                    self.style.WARNING(f"Код сброшен и снова активен: {obj.code}")
                )
            else:
                self.stdout.write(self.style.WARNING(f"Код уже есть: {obj.code}"))
            return
        self.stdout.write(self.style.SUCCESS(f"Код создан: {obj.code}"))
