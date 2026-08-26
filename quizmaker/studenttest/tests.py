"""Access-control regression tests.

Each test here pins down a hole that existed before the security pass: an
unauthenticated PDF endpoint, cross-user report access, state changes over GET,
and unvalidated uploads.
"""


from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import SubmissionForm
from .models import Course, Enrollment, Exercise, Submission, Test


class AccessControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("teacher", password="pw-teacher-123")
        cls.student = User.objects.create_user("student", password="pw-student-123")
        cls.other = User.objects.create_user("other", password="pw-other-1234")
        cls.staff = User.objects.create_user(
            "staff", password="pw-staff-12345", is_staff=True, is_superuser=True
        )

        cls.course = Course.objects.create(name="Corso", enabled=True, creator=cls.teacher)
        Enrollment.objects.create(student=cls.student, course=cls.course)

        cls.test = Test.objects.create(
            name="Verifica",
            description="d",
            enabled=True,
            is_graded=False,
            due_date=timezone.now() + timezone.timedelta(days=7),
            course=cls.course,
            creator=cls.teacher,
        )
        cls.exercise = Exercise.objects.create(
            test=cls.test,
            title="Es 1",
            description="testo",
            score=10,
            type="C",
            creator=cls.teacher,
        )
        Submission.objects.create(
            user=cls.student, exercise=cls.exercise, answer_text="risposta segreta"
        )

    def report_url(self, user):
        return reverse(
            "user_test_report", kwargs={"test_pk": self.test.pk, "user_pk": user.pk}
        )

    def test_report_rejects_anonymous(self):
        """The PDF endpoint used to serve any student's answers with no login."""
        response = self.client.get(self.report_url(self.student))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    def test_report_rejects_other_student(self):
        """A logged-in user must not read another user's submissions."""
        self.client.force_login(self.other)
        response = self.client.get(self.report_url(self.student))
        self.assertEqual(response.status_code, 403)

    def test_report_allows_own(self):
        self.client.force_login(self.student)
        response = self.client.get(self.report_url(self.student))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_report_allows_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.report_url(self.student))
        self.assertEqual(response.status_code, 200)

    def test_enroll_rejects_get(self):
        """Enrolment changes state, so a GET must not perform it."""
        self.client.force_login(self.other)
        before = Enrollment.objects.count()
        self.client.get(reverse("enroll_in_course", args=[self.course.pk]))
        self.assertEqual(Enrollment.objects.count(), before)

    def test_enroll_accepts_post(self):
        self.client.force_login(self.other)
        self.client.post(reverse("enroll_in_course", args=[self.course.pk]))
        self.assertTrue(self.course.is_student_enrolled(self.other))

    def test_course_hidden_when_not_enrolled(self):
        self.client.force_login(self.other)
        response = self.client.get(
            reverse("test_list_by_course", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_exercise_list_denied_for_locked_test(self):
        self.test.enabled = False
        self.test.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse("exercise_list", args=[self.test.pk]))
        self.assertEqual(response.status_code, 403)

    def test_graded_test_without_due_date_is_not_past_due(self):
        """`due_date` is nullable; comparing it to now used to raise TypeError."""
        self.test.is_graded = True
        self.test.due_date = None
        self.test.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse("exercise_list", args=[self.test.pk]))
        self.assertEqual(response.status_code, 200)

    def test_duplicate_exercise_route_is_gone(self):
        """Duplication is an admin action now, not a public state-changing GET."""
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("duplicate_exercise", args=[self.exercise.pk])


class SubmissionFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("t2", password="pw-teacher-123")
        cls.student = User.objects.create_user("s2", password="pw-student-123")
        cls.course = Course.objects.create(name="C", enabled=True, creator=cls.teacher)
        cls.test = Test.objects.create(
            name="T", description="d", enabled=True, course=cls.course, creator=cls.teacher
        )
        cls.exercise = Exercise.objects.create(
            test=cls.test, title="E", description="d", score=1, type="C", creator=cls.teacher
        )

    def build(self, upload):
        return SubmissionForm(
            {"answer_text": ""},
            {"file": upload},
            user=self.student,
            exercise=self.exercise,
        )

    def test_rejects_disallowed_extension(self):
        form = self.build(SimpleUploadedFile("payload.exe", b"MZ..."))
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    @override_settings(MAX_UPLOAD_SIZE=10)
    def test_rejects_oversized_file(self):
        form = self.build(SimpleUploadedFile("a.txt", b"x" * 100))
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_accepts_allowed_file_and_forces_owner(self):
        form = self.build(SimpleUploadedFile("solution.py", b"print(1)"))
        self.assertTrue(form.is_valid(), form.errors)
        submission = form.save()
        # The owner comes from the view, never from the POST payload.
        self.assertEqual(submission.user, self.student)
        self.assertEqual(submission.exercise, self.exercise)


class SettingsTests(TestCase):
    def test_secret_key_is_not_the_leaked_one(self):
        from django.conf import settings

        self.assertNotIn("3t91vu", settings.SECRET_KEY)
        self.assertFalse(settings.SECRET_KEY.startswith("django-insecure-"))
