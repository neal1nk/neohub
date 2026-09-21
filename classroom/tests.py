from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from classroom.models import Assignment, Material, Notification, Submission


class NeoHubFlowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", password="pass12345")
        self.teacher.profile.role = Profile.Role.TEACHER
        self.teacher.profile.display_name = "Teacher"
        self.teacher.profile.save()

    def test_teacher_creates_student_and_grades_100(self):
        self.client.login(username="teacher", password="pass12345")
        response = self.client.post(
            reverse("classroom:student_create"),
            {
                "display_name": "Ученик",
                "username": "pupil",
                "password": "pupil123",
                "password_confirm": "pupil123",
            },
        )
        self.assertEqual(response.status_code, 302)
        student = User.objects.get(username="pupil")
        self.assertTrue(student.profile.is_student)

        response = self.client.post(
            reverse("classroom:material_create", args=[student.pk]),
            {"title": "Лекция", "body": "Текст", "link": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Material.objects.filter(student=student, title="Лекция").exists())
        self.assertTrue(
            Notification.objects.filter(
                recipient=student, kind=Notification.Kind.MATERIAL
            ).exists()
        )

        response = self.client.post(
            reverse("classroom:assignment_create", args=[student.pk, "practice"]),
            {"title": "Практика", "description": "Сделай", "deadline": ""},
        )
        self.assertEqual(response.status_code, 302)
        assignment = Assignment.objects.get(title="Практика")
        self.assertIsNone(assignment.deadline)
        self.assertEqual(assignment.compute_status(), Assignment.Status.OPEN)

        self.client.logout()
        self.client.login(username="pupil", password="pupil123")
        response = self.client.post(
            reverse("classroom:assignment_submit", args=[assignment.pk]),
            {"text": "Готово"},
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.compute_status(), Assignment.Status.SUBMITTED)
        self.assertTrue(assignment.is_locked_for_student())

        # cannot resubmit practice
        response = self.client.post(
            reverse("classroom:assignment_submit", args=[assignment.pk]),
            {"text": "Изменено"},
        )
        self.assertEqual(response.status_code, 302)
        assignment.submission_obj.refresh_from_db()
        self.assertEqual(assignment.submission_obj.text, "Готово")

        self.client.logout()
        self.client.login(username="teacher", password="pass12345")
        response = self.client.post(
            reverse("classroom:assignment_grade", args=[assignment.pk]),
            {"grade": "85", "teacher_comment": "Хорошо"},
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.compute_status(), Assignment.Status.GRADED)
        self.assertEqual(assignment.submission.grade, 85)
        self.assertEqual(student.profile.rating_score(), 85)

        # overview tab
        response = self.client.get(
            reverse("classroom:student_detail", args=[student.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Рейтинг")

        # personal data
        response = self.client.post(
            reverse("classroom:student_detail", args=[student.pk]) + "?tab=profile",
            {
                "display_name": "Ученик Новый",
                "username": "pupil",
                "password": "",
                "password_confirm": "",
                "email": "pupil@example.com",
                "telegram": "@pupil",
                "whatsapp": "+7999",
                "max_messenger": "pupil_max",
            },
        )
        self.assertEqual(response.status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.email, "pupil@example.com")
        self.assertEqual(student.profile.telegram, "@pupil")

    def test_student_cannot_open_teacher_dashboard(self):
        student = User.objects.create_user(username="onlystudent", password="pupil123")
        student.profile.role = Profile.Role.STUDENT
        student.profile.teacher = self.teacher
        student.profile.save()
        self.client.login(username="onlystudent", password="pupil123")
        response = self.client.get(reverse("classroom:teacher_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_grade_must_be_0_100(self):
        teacher = self.teacher
        student = User.objects.create_user(username="s2", password="pupil123")
        student.profile.role = Profile.Role.STUDENT
        student.profile.teacher = teacher
        student.profile.save()
        assignment = Assignment.objects.create(
            student=student,
            assignment_type=Assignment.AssignmentType.HOMEWORK,
            title="ДЗ",
            created_by=teacher,
        )
        Submission.objects.create(assignment=assignment, text="x", submitted_at=timezone.now())
        self.client.login(username="teacher", password="pass12345")
        response = self.client.post(
            reverse("classroom:assignment_grade", args=[assignment.pk]),
            {"grade": "150", "teacher_comment": ""},
        )
        self.assertEqual(response.status_code, 200)
        assignment.submission_obj.refresh_from_db()
        self.assertIsNone(assignment.submission_obj.grade)

    def test_new_teacher_sees_empty_cabinet(self):
        # Existing teacher has a student
        self.client.login(username="teacher", password="pass12345")
        self.client.post(
            reverse("classroom:student_create"),
            {
                "display_name": "Старый ученик",
                "username": "oldpupil",
                "password": "pupil123",
                "password_confirm": "pupil123",
            },
        )
        self.client.logout()

        other = User.objects.create_user(username="teacher2", password="pass12345")
        other.profile.role = Profile.Role.TEACHER
        other.profile.display_name = "Teacher 2"
        other.profile.save()
        self.client.login(username="teacher2", password="pass12345")
        response = self.client.get(reverse("classroom:teacher_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["student_count"], 0)
        self.assertNotContains(response, "oldpupil")
        self.assertNotContains(response, "Старый ученик")
