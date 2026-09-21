from django.db import migrations


def backfill_student_teachers(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Assignment = apps.get_model("classroom", "Assignment")
    User = apps.get_model("auth", "User")

    teachers = list(
        User.objects.filter(profile__role="teacher").order_by("id")
    )
    if not teachers:
        return
    fallback = teachers[0]

    for profile in Profile.objects.filter(role="student", teacher__isnull=True):
        owner_id = (
            Assignment.objects.filter(student_id=profile.user_id, created_by__isnull=False)
            .exclude(created_by_id=profile.user_id)
            .values_list("created_by_id", flat=True)
            .first()
        )
        if owner_id and any(t.id == owner_id for t in teachers):
            profile.teacher_id = owner_id
        else:
            profile.teacher_id = fallback.id
        profile.save(update_fields=["teacher_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_profile_teacher"),
        ("classroom", "0007_grade_feedback_and_notification_kind"),
    ]

    operations = [
        migrations.RunPython(backfill_student_teachers, noop_reverse),
    ]
