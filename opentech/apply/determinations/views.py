from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, CreateView

from opentech.apply.activity.models import Activity
from opentech.apply.activity.messaging import messenger, MESSAGES
from opentech.apply.funds.models import ApplicationSubmission
from opentech.apply.funds.workflow import DETERMINATION_OUTCOMES
from opentech.apply.utils.views import CreateOrUpdateView, ViewDispatcher
from opentech.apply.users.decorators import staff_required

from .forms import (
    BatchConceptDeterminationForm,
    BatchProposalDeterminationForm,
    ConceptDeterminationForm,
    ProposalDeterminationForm,
)
from .models import Determination, DeterminationMessageSettings, NEEDS_MORE_INFO, TRANSITION_DETERMINATION

from .utils import (
    can_create_determination,
    can_edit_determination,
    has_final_determination,
    outcome_from_actions,
    transition_from_outcome,
)


def get_form_for_stages(submissions):
    forms = [
        get_form_for_stage(submission, batch=True)
        for submission in submissions
    ]
    if len(set(forms)) != 1:
        raise ValueError('Submissions expect different forms - please contact and admin')

    return forms[0]


def get_form_for_stage(submission, batch=False):
    if batch:
        forms = [BatchConceptDeterminationForm, BatchProposalDeterminationForm]
    else:
        forms = [ConceptDeterminationForm, ProposalDeterminationForm]
    index = submission.workflow.stages.index(submission.stage)
    return forms[index]


@method_decorator(staff_required, name='dispatch')
class BatchDeterminationCreateView(CreateView):
    template_name = 'determinations/batch_determination_form.html'

    def dispatch(self, *args, **kwargs):
        if not self.get_action() or not self.get_submissions():
            messages.warning(self.request, 'Improperly configured request, please try again.')
            return HttpResponseRedirect(self.get_success_url())
        return super().dispatch(*args, **kwargs)

    def get_action(self):
        return self.request.GET.get('action', '')

    def get_submissions(self):
        try:
            submission_ids = self.request.GET.get('submissions').split(',')
        except AttributeError:
            return None
        try:
            ids = [int(pk) for pk in submission_ids]
        except ValueError:
            return None
        return ApplicationSubmission.objects.filter(id__in=ids)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['submissions'] = self.get_submissions()
        kwargs['action'] = self.get_action()
        kwargs.pop('instance')
        return kwargs

    def get_form_class(self):
        return get_form_for_stages(self.get_submissions())

    def get_context_data(self, **kwargs):
        action_name = 'INVITE TO PROPOSAL'
        return super().get_context_data(
            action_name=action_name,
            submissions=self.get_submissions(),
            **kwargs,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        submissions = self.get_submissions()
        determinations = form.instances
        messenger(
            MESSAGES.BATCH_DETERMINATION_OUTCOME,
            request=self.request,
            user=self.request.user,
            submissions=submissions,
            related=determinations,
        )
        determinations = {
            determination.submission.id: determination
            for determination in determinations
        }
        for submission in submissions:
            transition = transition_from_outcome(form.cleaned_data.get('outcome'), submission)
            determination = determinations[submission.id]

            if determination.outcome == NEEDS_MORE_INFO:
                # We keep a record of the message sent to the user in the comment
                Activity.comments.create(
                    message=determination.stripped_message,
                    user=self.request.user,
                    submission=submission,
                    related_object=determination,
                )

            submission.perform_transition(transition, self.request.user, request=self.request, notify=False)
        return response

    @classmethod
    def should_redirect(cls, request, submissions, actions):
        excluded = []
        for submission in submissions:
            if has_final_determination(submission):
                excluded.append(submission)

        non_determine_states = set(actions) - set(DETERMINATION_OUTCOMES.keys())
        if not any(non_determine_states):
            if excluded:
                messages.warning(
                    request,
                    _('A determination already exists for the following submissions and they have been excluded: {submissions}').format(
                        submissions=', '.join([submission.title for submission in excluded]),
                    )
                )

            submissions = submissions.exclude(id__in=[submission.id for submission in excluded])
            action = outcome_from_actions(actions)
            return HttpResponseRedirect(
                reverse_lazy('apply:submissions:determinations:batch') +
                "?action=" + action + "&submissions=" + ','.join([str(submission.id) for submission in submissions])
            )
        elif set(actions) != non_determine_states:
            raise ValueError('Inconsistent states provided - please talk to an admin')

    def get_success_url(self):
        return reverse_lazy('apply:submissions:list')


@method_decorator(staff_required, name='dispatch')
class DeterminationCreateOrUpdateView(CreateOrUpdateView):
    model = Determination
    template_name = 'determinations/determination_form.html'

    def get_object(self, queryset=None):
        return self.model.objects.get(submission=self.submission, is_draft=True)

    def dispatch(self, request, *args, **kwargs):
        self.submission = get_object_or_404(ApplicationSubmission, id=self.kwargs['submission_pk'])

        if not can_create_determination(request.user, self.submission):
            return self.back_to_submission(_('You do not have permission to create that determination.'))

        if has_final_determination(self.submission):
            return self.back_to_submission(_('A final determination has already been submitted.'))

        try:
            self.determination = self.get_object()
        except Determination.DoesNotExist:
            pass
        else:
            if not can_edit_determination(request.user, self.determination, self.submission):
                return self.back_to_detail(_('There is a draft determination you do not have permission to edit.'))

        return super().dispatch(request, *args, **kwargs)

    def back_to_submission(self, message):
        messages.warning(self.request, message)
        return HttpResponseRedirect(self.submission.get_absolute_url())

    def back_to_detail(self, message):
        messages.warning(self.request, message)
        return HttpResponseRedirect(self.determination.get_absolute_url())

    def get_context_data(self, **kwargs):
        determination_messages = DeterminationMessageSettings.for_site(self.request.site)

        return super().get_context_data(
            submission=self.submission,
            message_templates=determination_messages.get_for_stage(self.submission.stage.name),
            **kwargs
        )

    def get_form_class(self):
        return get_form_for_stage(self.submission)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['submission'] = self.submission
        kwargs['action'] = self.request.GET.get('action')
        return kwargs

    def get_success_url(self):
        return self.submission.get_absolute_url()

    def form_valid(self, form):
        super().form_valid(form)

        if not self.object.is_draft:
            messenger(
                MESSAGES.DETERMINATION_OUTCOME,
                request=self.request,
                user=self.object.author,
                submission=self.object.submission,
                related=self.object,
            )
            transition = transition_from_outcome(form.cleaned_data.get('outcome'), self.submission)

            if self.object.outcome == NEEDS_MORE_INFO:
                # We keep a record of the message sent to the user in the comment
                Activity.comments.create(
                    message=self.object.stripped_message,
                    user=self.request.user,
                    submission=self.submission,
                    related_object=self.object,
                )

            self.submission.perform_transition(transition, self.request.user, request=self.request, notify=False)

        return HttpResponseRedirect(self.submission.get_absolute_url())

    @classmethod
    def should_redirect(cls, request, submission, action):
        if has_final_determination(submission):
            determination = submission.determinations.final().first()
            if determination.outcome == TRANSITION_DETERMINATION[action]:
                # We want to progress as normal so don't redirect through form
                return False
            else:
                # Add a helpful message to prompt them to select the correct option
                messages.warning(
                    request,
                    _('A determination of "{current}" exists but you tried to progress as "{target}"').format(
                        current=determination.get_outcome_display(),
                        target=action,
                    )
                )

        if action in DETERMINATION_OUTCOMES:
            return HttpResponseRedirect(reverse_lazy(
                'apply:submissions:determinations:form',
                args=(submission.id,)) + "?action=" + action)


@method_decorator(staff_required, name='dispatch')
class AdminDeterminationDetailView(DetailView):
    model = Determination

    def get_object(self, queryset=None):
        return self.model.objects.get(submission=self.submission, id=self.kwargs['pk'])

    def dispatch(self, request, *args, **kwargs):
        self.submission = get_object_or_404(ApplicationSubmission, id=self.kwargs['submission_pk'])
        determination = self.get_object()

        if can_edit_determination(request.user, determination, self.submission) and determination.is_draft:
            return HttpResponseRedirect(reverse_lazy('apply:submissions:determinations:form', args=(self.submission.id,)))

        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class ReviewerDeterminationDetailView(DetailView):
    model = Determination

    def get_object(self, queryset=None):
        return self.model.objects.get(submission=self.submission)

    def dispatch(self, request, *args, **kwargs):
        self.submission = get_object_or_404(ApplicationSubmission, id=self.kwargs['submission_pk'])
        determination = self.get_object()

        if not determination.submitted:
            return HttpResponseRedirect(reverse_lazy('apply:submissions:detail', args=(self.submission.id,)))

        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class ApplicantDeterminationDetailView(DetailView):
    model = Determination

    def get_object(self, queryset=None):
        return self.model.objects.get(submission=self.submission, id=self.kwargs['pk'])

    def dispatch(self, request, *args, **kwargs):
        self.submission = get_object_or_404(ApplicationSubmission, id=self.kwargs['submission_pk'])
        determination = self.get_object()

        if request.user != self.submission.user:
            raise PermissionDenied

        if determination.is_draft:
            return HttpResponseRedirect(reverse_lazy('apply:submissions:determinations:detail', args=(self.submission.id,)))

        return super().dispatch(request, *args, **kwargs)


class DeterminationDetailView(ViewDispatcher):
    admin_view = AdminDeterminationDetailView
    applicant_view = ApplicantDeterminationDetailView
    reviewer_view = ReviewerDeterminationDetailView
