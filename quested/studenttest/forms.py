# forms.py

import logging
import os

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm, UserChangeForm  # noqa: F401
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from .models import Course, Submission

logger = logging.getLogger(__name__)


class AssignTestsToCourseForm(forms.Form):
    course = forms.ModelChoiceField(queryset=Course.objects.all())


class SubmissionForm(forms.ModelForm):
    """Submission editor.

    `user` and `exercise` are supplied by the view and stored on the form, so a
    request can never rebind a submission to a different owner or exercise.
    """

    class Meta:
        model = Submission
        fields = ['file', 'answer_text', 'answer_choice']

    def __init__(self, *args, user=None, exercise=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.exercise = exercise
        if exercise is not None:
            # Only this exercise's choices are selectable.
            self.fields['answer_choice'].queryset = exercise.choices.all()

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')
        if not uploaded:
            return uploaded

        max_size = settings.MAX_UPLOAD_SIZE
        if uploaded.size > max_size:
            raise forms.ValidationError(
                _('Il file supera la dimensione massima di %(mb)s MB.')
                % {'mb': round(max_size / (1024 * 1024), 1)}
            )

        extension = os.path.splitext(uploaded.name)[1].lower()
        if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise forms.ValidationError(
                _('Estensione "%(ext)s" non ammessa.') % {'ext': extension or '(nessuna)'}
            )

        return uploaded

    def save(self, commit=True):
        submission = super().save(commit=False)
        if self.user is not None:
            submission.user = self.user
        if self.exercise is not None:
            submission.exercise = self.exercise

        if commit:
            submission.save()

        return submission


class UpdateProfileForm(UserChangeForm):
    password = None  # this line will exclude the password field
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)

    class Meta:
        model = User
        fields = ('first_name', 'last_name')

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user
