from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


def user_directory_path(instance, filename):
    # This will convert the username to lowercase
    # and will replace spaces with underscores
    username = slugify(instance.user.username.lower())
    return f'{username}/test_{timezone.now().strftime("%Y%m%d")}/{filename}'


class Course(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    enabled = models.BooleanField(default=True)
    visible_to = models.ManyToManyField(User, blank=True, related_name='visible_courses')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    def is_student_enrolled(self, user):
        """ Controlla se l'utente è iscritto al corso. """
        return Enrollment.objects.filter(student=user, course=self).exists()

    def is_visible_to(self, user):
        """An empty `visible_to` means the course is open to every user."""
        if not self.visible_to.exists():
            return True
        return self.visible_to.filter(pk=user.pk).exists()


class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrollment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'course']

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.course.name}"


class Test(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    enabled = models.BooleanField(default=False)
    is_graded = models.BooleanField(default=False)
    due_date = models.DateTimeField(null=True, blank=True)
    visible_to = models.ManyToManyField(User, blank=True, related_name='visible_tests')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    def is_visible_to(self, user):
        """Visible when explicitly shared, or when shared with nobody in particular.

        A test also inherits its course's restrictions: a student who cannot see
        the course must not reach its tests by guessing a test id.
        """
        if self.course is not None and not self.course.is_visible_to(user):
            return False
        if not self.visible_to.exists():
            return True
        return self.visible_to.filter(pk=user.pk).exists()


class Exercise(models.Model):
    TYPE_CHOICES = [
        ('O', _('Domanda aperta')),
        ('M', _('Scelta multipla')),
        ('C', _('Codice')),
        ('D', _('Diagramma di flusso')),
    ]

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='exercises')
    title = models.CharField(max_length=255)
    description = models.TextField()
    score = models.PositiveIntegerField(null=True, blank=True)
    type = models.CharField(max_length=1, choices=TYPE_CHOICES, blank=True, null=True)
    expected_answer = models.TextField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return self.title


class UserExercise(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    signed = models.BooleanField(default=False)
    stars = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(5)])

    class Meta:
        unique_together = (('user', 'exercise'),)

    def __str__(self):
        return f"{self.user.username} - {self.exercise.title}"


class Choice(models.Model):
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='choices', blank=True, null=True)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class Submission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)
    answer_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, blank=True, null=True)
    file = models.FileField(upload_to=user_directory_path, blank=True, null=True)

    class Meta:
        # The app already assumes one submission per user per exercise; enforce it
        # so a race cannot create a second one.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "exercise"], name="unique_submission_per_user_exercise"
            )
        ]

    def __str__(self):
        return f"{self.user.username}'s submission for {self.exercise.title}"


