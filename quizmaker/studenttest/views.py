# views.py
import html
import io
import logging

import chardet
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views import View

# ReportLab
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
)

from .forms import PasswordChangeForm, SubmissionForm
from .models import Course, Enrollment, Exercise, Submission, Test, User, UserExercise

logger = logging.getLogger(__name__)


def _test_is_locked(test, now):
    """A test is locked when it is disabled, or graded and past its due date.

    `due_date` is nullable, so a graded test without a date is never past due.
    """
    if not test.enabled:
        return True
    return bool(test.is_graded and test.due_date is not None and test.due_date < now)


def _safe_referer(request, fallback="/"):
    """Return the Referer only when it points back at this site.

    Redirecting to an unvalidated Referer is an open redirect.
    """
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return referer
    return fallback


class MyDocTemplate(BaseDocTemplate):
    def __init__(self, filename, user, test, **kwargs):
        self.user = user
        self.test = test
        BaseDocTemplate.__init__(self, filename, **kwargs)
        template = PageTemplate(
            "normal",
            [Frame(20 * mm, 20 * mm, (A4[0] - 40 * mm), (A4[1] - 40 * mm), id="main")],
        )
        template.beforeDrawPage = self.before_page
        self.addPageTemplates([template])

    def before_page(self, canvas, document):
        canvas.saveState()
        styles = getSampleStyleSheet()

        # Header
        due = self.test.due_date.strftime("%d/%m/%Y") if self.test.due_date else "-"
        header = Paragraph(f"Date: {due}", styles["Normal"])
        w, h = header.wrap(document.width, document.topMargin)
        header.drawOn(canvas, document.leftMargin, document.pagesize[1] - h - 10 * mm)

        right_aligned_style = ParagraphStyle(
            "RightAligned", parent=styles["Normal"], alignment=TA_RIGHT
        )
        header2 = Paragraph(
            f"{self.user.first_name} {self.user.last_name}", right_aligned_style
        )
        w, h = header2.wrap(200, document.topMargin)
        header2.drawOn(
            canvas, document.pagesize[0] - w - 20 * mm, document.pagesize[1] - h - 10 * mm
        )

        # Footer
        footer = Paragraph(f"Page: {document.page}", styles["Normal"])
        w, h = footer.wrap(document.width, document.bottomMargin)
        footer.drawOn(canvas, document.pagesize[0] - w - 20 * mm, h)

        canvas.restoreState()


@login_required
def profile(request):
    # Use Django's UserChangeForm to update user information
    form = UserChangeForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        if "update_profile" in request.POST:
            form = UserChangeForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Your profile was successfully updated!")
                return redirect("profile")
            else:
                messages.error(request, "Please correct the errors below.")

        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Important to prevent logout
                messages.success(request, "Your password was successfully updated!")
                return redirect("profile")
            else:
                messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "registration/profile.html",
        {"form": form, "password_form": password_form},
    )


@login_required
def course_list(request):
    # visible to everyone (visible_to is empty) or visible to the current user.
    courses = Course.objects.filter(
        Q(visible_to__isnull=True) | Q(visible_to=request.user),
        enabled=True,
    ).prefetch_related(
        Prefetch(
            "enrollments",
            queryset=Enrollment.objects.filter(student=request.user),
            to_attr="user_enrollment",
        )
    )

    num_courses = courses.count()
    num_placeholders = (3 - (num_courses % 3)) % 3

    return render(
        request,
        "course_list.html",
        {
            "courses": courses,
            "num_placeholders": num_placeholders,
            "user": request.user,
        },
    )


@login_required
def enroll_in_course(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    # Enrolling changes state, so it must not be reachable by a plain GET.
    if request.method != "POST":
        return redirect("test_list_by_course", course_id=course_id)

    # A disabled course, or one not visible to this user, cannot be joined.
    if not course.enabled or not course.is_visible_to(request.user):
        raise PermissionDenied

    # Controlla se l'utente ha già effettuato l'iscrizione
    if not course.is_student_enrolled(request.user):
        Enrollment.objects.create(student=request.user, course=course)

    # Reindirizza l'utente alla lista dei test per il corso
    return redirect("test_list_by_course", course_id=course_id)


@login_required
def test_list(request):
    # Show only the tests that are either
    # visible to everyone (visible_to is empty) or visible to the current user.
    tests = Test.objects.filter(
        Q(visible_to__isnull=True) | Q(visible_to=request.user),
        enabled=True,
    )
    return render(request, "test_list.html", {"tests": tests})


@login_required
def test_list_by_course(request, course_id):
    # Recupera il corso specificato o restituisce una pagina 404 se non trovato
    course = get_object_or_404(
        Course.objects.prefetch_related(
            Prefetch(
                "enrollments",
                queryset=Enrollment.objects.filter(student=request.user),
                to_attr="user_enrollment",
            )
        ),
        pk=course_id,
    )

    cannot_enter_view = not request.user.is_staff and (
        not course.enabled or not course.is_student_enrolled(request.user)
    )

    if cannot_enter_view:
        logger.info(
            "User %s denied access to course %s (enabled=%s, enrolled=%s)",
            request.user,
            course_id,
            course.enabled,
            course.is_student_enrolled(request.user),
        )
        return render(
            request,
            "error.html",
            {
                "message": f"Spiacente! Non hai i permessi per accedere al corso {course.name}",
                "back_url": _safe_referer(request),
            },
            status=403,
        )

    # Filtra i test associati a quel corso specifico
    tests = Test.objects.filter(course=course).order_by("name")

    num_tests = tests.count()
    num_placeholders = (3 - (num_tests % 3)) % 3

    # Restituisce i test al template
    return render(
        request,
        "test_list.html",
        {
            "course": course,
            "tests": tests,
            "num_placeholders": num_placeholders,
            "has_footer": True,
        },
    )


@login_required
def exercise_list(request, test_id):
    now = timezone.now()
    test = get_object_or_404(Test, id=test_id)
    total_score = test.exercises.aggregate(total=Sum("score"))["total"] or 0

    if not request.user.is_staff and (
        _test_is_locked(test, now) or not test.is_visible_to(request.user)
    ):
        logger.info("User %s denied access to test %s", request.user, test_id)
        return render(
            request,
            "error.html",
            {
                "message": f"Spiacente! Non hai i permessi per accedere al test {test.name}"
            },
            status=403,
        )

    exercises = Exercise.objects.filter(test=test, enabled=True).annotate(
        signed_count=Count("userexercise", filter=Q(userexercise__signed=True)),
        average_rating=Avg("userexercise__stars"),  # Compute the average rating here
    )
    completed_exercises = Submission.objects.filter(
        user=request.user, exercise__in=exercises
    ).values_list("exercise", flat=True)

    # Fetch the UserExercise objects related to the current user and test
    user_exercises = UserExercise.objects.filter(user=request.user, exercise__test=test)

    # Extract the ids of the signed exercises into a list
    signed_exercises = [ue.exercise_id for ue in user_exercises if ue.signed]

    return render(
        request,
        "exercise_list.html",
        {
            "test": test,
            "exercises": exercises,
            "completed_exercises": completed_exercises,
            "signed_exercises": signed_exercises,
            "total_score": total_score,
            "has_footer": True,
            "fixed_footer": True,
        },
    )


@login_required
def submit_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if not request.user.is_staff and (
        _test_is_locked(test, timezone.now()) or not test.is_visible_to(request.user)
    ):
        raise PermissionDenied

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.user = request.user
            submission.save()
            return redirect("test_list")
    else:
        form = SubmissionForm()
    return render(request, "submit_test.html", {"test": test, "form": form})


@login_required
def submit_exercise(request, exercise_id):
    now = timezone.now()
    exercise = get_object_or_404(Exercise, id=exercise_id)
    test = exercise.test  # Get the related test

    # One gate for every method, so a POST cannot bypass what a GET is denied.
    if not request.user.is_staff and (
        _test_is_locked(test, now) or not test.is_visible_to(request.user)
    ):
        logger.info(
            "User %s denied access to test %s via exercise %s",
            request.user,
            test.id,
            exercise_id,
        )
        return render(
            request,
            "error.html",
            {
                "message": "La data di consegna è passata, oppure il test non è abilitato."
            },
            status=403,
        )

    submission = Submission.objects.filter(user=request.user, exercise=exercise).first()
    user_exercise, _created = UserExercise.objects.get_or_create(
        user=request.user, exercise=exercise
    )

    form = SubmissionForm(instance=submission, user=request.user, exercise=exercise)

    if request.method == "POST":
        if not test.is_graded:
            # Ungraded tests only record the student's self-assessment.
            try:
                rating = int(request.POST.get("rating") or 0)
            except (TypeError, ValueError):
                rating = 0
            user_exercise.stars = rating if 1 <= rating <= 5 else None
            user_exercise.signed = request.POST.get("signed") is not None
            user_exercise.save()
            # Stay on the same exercise page after successful submission
            return redirect("submit_exercise", exercise_id=exercise_id)

        form = SubmissionForm(
            request.POST,
            request.FILES,
            instance=submission,
            user=request.user,
            exercise=exercise,
        )
        if form.is_valid():
            form.save()
            # Stay on the same exercise page after successful submission
            return redirect("submit_exercise", exercise_id=exercise_id)

    return render(
        request,
        "submit_exercise.html",
        {
            "exercise": exercise,
            "form": form,
            "submission": submission,
            "user_exercise": user_exercise,
            "has_footer": True,
            "fixed_footer": True,
        },
    )


class UserTestReportView(LoginRequiredMixin, View):
    """PDF of one student's submissions for one test.

    Reachable from the admin, so it is restricted to staff and to the student
    the report is about; without that check any user id could be enumerated.
    """

    def get(self, request, *args, **kwargs):
        test = get_object_or_404(Test, pk=kwargs["test_pk"])
        user = get_object_or_404(User, pk=kwargs["user_pk"])

        if not request.user.is_staff and request.user.pk != user.pk:
            raise PermissionDenied

        submissions = user.submission_set.filter(exercise__test=test)

        buffer = io.BytesIO()

        doc = MyDocTemplate(buffer, user, test, pagesize=A4)

        styles = getSampleStyleSheet()
        elements = []

        # format the date in a human-readable format
        test_name = Paragraph(f"{test.name}", styles["Title"])
        elements.append(test_name)

        due = test.due_date.strftime("%d/%m/%Y") if test.due_date else "-"
        test_details = Paragraph(
            f"del {due} di {user.first_name} {user.last_name}", styles["Title"]
        )
        elements.append(test_details)
        elements.append(Spacer(1, 24))

        heading_style = ParagraphStyle(
            "heading", parent=styles["Heading2"], fontName="Helvetica", fontSize=12
        )
        body_style = ParagraphStyle(
            "body", parent=styles["Heading2"], fontName="Helvetica", fontSize=10
        )
        monospace_style = ParagraphStyle(
            "monospace", parent=styles["BodyText"], fontName="Courier", fontSize=10
        )

        for submission in submissions:
            exercise_title = Paragraph(
                f"Esercizio {submission.exercise.title} - Punti {submission.exercise.score}",
                heading_style,
            )
            elements.append(exercise_title)

            exercise_text = Paragraph(
                f"Testo: {submission.exercise.description}", body_style
            )
            elements.append(exercise_text)
            elements.append(Spacer(1, 12))

            if submission.exercise.type in ["O", "D"]:
                escaped_text = html.escape(submission.answer_text or "")
                elements.append(Paragraph(f"Risposta: {escaped_text}", monospace_style))
            elif submission.exercise.type == "M":
                choice = (
                    submission.answer_choice.text
                    if submission.answer_choice
                    else "No response provided"
                )
                elements.append(
                    Paragraph(f"Risposta: {html.escape(choice)}", monospace_style)
                )
            elif submission.exercise.type == "C":
                elements.append(Paragraph("Risposta:", monospace_style))
                elements.append(self._code_block(submission, monospace_style))

            elements.append(Spacer(1, 12))

        doc.build(elements)

        buffer.seek(0)

        username_slug = slugify(user.username)
        testname_slug = slugify(test.name)
        # Date in YYYYMMDD format for the filename
        date_slug = test.due_date.strftime("%Y%m%d") if test.due_date else "nodate"

        filename = f"{username_slug}_{date_slug}_{testname_slug}.pdf"

        return FileResponse(buffer, as_attachment=True, filename=filename)

    @staticmethod
    def _code_block(submission, style):
        if submission.answer_text:
            content = submission.answer_text
        elif submission.file:
            # The stored file may be in any encoding the student's editor used.
            with default_storage.open(submission.file.name, "rb") as f:
                rawdata = f.read()
            charenc = chardet.detect(rawdata)["encoding"] or "utf-8"
            try:
                content = rawdata.decode(charenc, errors="replace")
            except LookupError:
                content = rawdata.decode("utf-8", errors="replace")
        else:
            return Paragraph("No response provided", style)
        return Preformatted(content.replace("\r\n", "\n").replace("\t", " "), style)


def register(request):
    register_form = UserCreationForm()
    login_form = AuthenticationForm()

    if request.method == "POST":
        if "register" in request.POST:
            register_form = UserCreationForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                return redirect("course_list")
        elif "login" in request.POST:
            login_form = AuthenticationForm(request, request.POST)
            if login_form.is_valid():
                user = login_form.get_user()
                login(request, user)
                return redirect("course_list")

    return render(
        request,
        "registration/register.html",
        {"register_form": register_form, "login_form": login_form},
    )
