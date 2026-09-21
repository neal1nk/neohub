from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from accounts.models import Profile


class Command(BaseCommand):
    help = "Create or update the first teacher account for NeoHub."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="teacher")
        parser.add_argument("--password", default="teacher123")
        parser.add_argument("--name", default="Преподаватель")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        name = options["name"]

        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_staff = True
        user.save()

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = Profile.Role.TEACHER
        profile.display_name = name
        profile.save()

        action = "создан" if created else "обновлён"
        self.stdout.write(
            self.style.SUCCESS(
                f"Преподаватель {action}: логин={username}, пароль={password}"
            )
        )
