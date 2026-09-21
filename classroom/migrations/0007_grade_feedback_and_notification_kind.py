from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classroom", "0006_credit_exam_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="student_comment",
            field=models.TextField(
                blank=True, verbose_name="Комментарий ученика к оценке"
            ),
        ),
        migrations.AddField(
            model_name="submission",
            name="clarification_requested",
            field=models.BooleanField(
                default=False, verbose_name="Запрошено пояснение оценки"
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("submission", "Сдача работы"),
                    ("material", "Новая теория"),
                    ("assignment", "Новое задание"),
                    ("assignment_open", "Открытие задания"),
                    ("overdue", "Просрочка"),
                    ("grade", "Оценка"),
                    ("grade_question", "Вопрос по оценке"),
                    ("retake", "Пересдача"),
                    ("other", "Другое"),
                ],
                default="other",
                max_length=20,
            ),
        ),
    ]
