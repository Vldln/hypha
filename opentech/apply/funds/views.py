from copy import copy

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.text import mark_safe
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, FormView, ListView, UpdateView

from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from wagtail.core.models import Page

from opentech.apply.activity.views import (
    AllActivityContextMixin,
    ActivityContextMixin,
    CommentFormView,
    DelegatedViewMixin,
)
from opentech.apply.activity.messaging import messenger, MESSAGES
from opentech.apply.determinations.views import DeterminationCreateOrUpdateView
from opentech.apply.review.views import ReviewContextMixin
from opentech.apply.users.decorators import staff_required
from opentech.apply.users.models import User
from opentech.apply.utils.views import DelegateableListView, DelegateableView, ViewDispatcher

from .differ import compare
from .forms import (
    BatchUpdateReviewersForm,
    ProgressSubmissionForm,
    ScreeningSubmissionForm,
    UpdateReviewersForm,
    UpdateSubmissionLeadForm,
)
from .models import (
    ApplicationSubmission,
    ApplicationSubmissionReviewer,
    ApplicationRevision,
    ReviewerRole,
    RoundsAndLabs,
    RoundBase,
    LabBase
)
from .tables import (
    AdminSubmissionsTable,
    RoundsTable,
    RoundsFilter,
    SubmissionFilterAndSearch,
    SummarySubmissionsTable,
)
from .workflow import STAGE_CHANGE_ACTIONS, PHASES_MAPPING


@method_decorator(staff_required, name='dispatch')
class BaseAdminSubmissionsTable(SingleTableMixin, FilterView):
    table_class = AdminSubmissionsTable
    filterset_class = SubmissionFilterAndSearch
    filter_action = ''

    excluded_fields = []

    @property
    def excluded(self):
        return {
            'exclude': self.excluded_fields
        }

    def get_table_kwargs(self, **kwargs):
        return {**self.excluded, **kwargs}

    def get_filterset_kwargs(self, filterset_class, **kwargs):
        new_kwargs = super().get_filterset_kwargs(filterset_class)
        new_kwargs.update(self.excluded)
        new_kwargs.update(kwargs)
        return new_kwargs

    def get_queryset(self):
        return self.filterset_class._meta.model.objects.current().for_table(self.request.user)

    def get_context_data(self, **kwargs):
        search_term = self.request.GET.get('query')

        return super().get_context_data(
            search_term=search_term,
            filter_action=self.filter_action,
            **kwargs,
        )


@method_decorator(staff_required, name='dispatch')
class BatchUpdateReviewersView(DelegatedViewMixin, FormView):
    form_class = BatchUpdateReviewersForm
    context_name = 'batch_reviewer_form'

    def form_invalid(self, form):
        messages.error(self.request, mark_safe(_('Sorry something went wrong') + form.errors.as_ul()))
        return super().form_invalid(form)

    def form_valid(self, form):
        """
        Loop through all submissions selected on the page,
        Add any reviewers that were selected,  only if they are not
        currently saved to that submission.
        Send out a message of updates.
        """
        reviewers = User.objects.filter(id__in=form.cleaned_data['staff_reviewers'])

        submission_ids = form.cleaned_data['submission_ids']
        submissions = ApplicationSubmission.objects.filter(id__in=submission_ids)

        for submission in submissions:
            submission.reviewers.add(*reviewers)

        messenger(
            MESSAGES.BATCH_REVIEWERS_UPDATED,
            request=self.request,
            user=self.request.user,
            submissions=submissions,
            added=reviewers,
        )

        return super().form_valid(form)


class SubmissionOverviewView(AllActivityContextMixin, BaseAdminSubmissionsTable):
    template_name = 'funds/submissions_overview.html'
    table_class = SummarySubmissionsTable
    table_pagination = False
    filter_action = reverse_lazy('funds:submissions:list')

    def get_table_data(self):
        return super().get_table_data().order_by(F('last_update').desc(nulls_last=True))[:5]

    def get_context_data(self, **kwargs):
        base_query = RoundsAndLabs.objects.with_progress().active().order_by('-end_date')
        open_rounds = base_query.open()[:6]
        open_query = '?round_state=open'
        closed_rounds = base_query.closed()[:6]
        closed_query = '?round_state=closed'
        rounds_title = 'All Rounds and Labs'

        return super().get_context_data(
            open_rounds=open_rounds,
            open_query=open_query,
            closed_rounds=closed_rounds,
            closed_query=closed_query,
            rounds_title=rounds_title,
            **kwargs,
        )


class SubmissionListView(AllActivityContextMixin, BaseAdminSubmissionsTable, DelegateableListView):
    template_name = 'funds/submissions.html'
    form_views = [
        BatchUpdateReviewersView
    ]


class SubmissionsByRound(AllActivityContextMixin, BaseAdminSubmissionsTable, DelegateableListView):
    template_name = 'funds/submissions_by_round.html'
    form_views = [
        BatchUpdateReviewersView
    ]

    excluded_fields = ('round', 'lead', 'fund')

    def get_queryset(self):
        # We want to only show lab or Rounds in this view, their base class is Page
        try:
            self.obj = Page.objects.get(pk=self.kwargs.get('pk')).specific
        except Page.DoesNotExist:
            raise Http404(_("No Round or Lab found matching the query"))

        if not isinstance(self.obj, (LabBase, RoundBase)):
            raise Http404(_("No Round or Lab found matching the query"))
        return super().get_queryset().filter(Q(round=self.obj) | Q(page=self.obj))

    def get_context_data(self, **kwargs):
        return super().get_context_data(object=self.obj, **kwargs)


class SubmissionsByStatus(BaseAdminSubmissionsTable):
    template_name = 'funds/submissions_by_status.html'
    status_mapping = PHASES_MAPPING

    def get(self, request, *args, **kwargs):
        self.status = kwargs.get('status')
        status_data = self.status_mapping[self.status]
        self.status_name = status_data['name']
        self.statuses = status_data['statuses']
        if self.status not in self.status_mapping:
            raise Http404(_("No statuses match the requested value"))

        return super().get(request, *args, **kwargs)

    def get_filterset_kwargs(self, filterset_class, **kwargs):
        return super().get_filterset_kwargs(filterset_class, limit_statuses=self.statuses, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(status__in=self.statuses)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            status=self.status_name,
            statuses=self.statuses,
            **kwargs,
        )


@method_decorator(staff_required, name='dispatch')
class ProgressSubmissionView(DelegatedViewMixin, UpdateView):
    model = ApplicationSubmission
    form_class = ProgressSubmissionForm
    context_name = 'progress_form'

    def form_valid(self, form):
        action = form.cleaned_data.get('action')
        # Defer to the determination form for any of the determination transitions
        redirect = DeterminationCreateOrUpdateView.should_redirect(self.request, self.object, action)
        if redirect:
            return redirect

        self.object.perform_transition(action, self.request.user, request=self.request)
        return super().form_valid(form)


@method_decorator(staff_required, name='dispatch')
class ScreeningSubmissionView(DelegatedViewMixin, UpdateView):
    model = ApplicationSubmission
    form_class = ScreeningSubmissionForm
    context_name = 'screening_form'

    def form_valid(self, form):
        old = copy(self.get_object())
        response = super().form_valid(form)
        # Record activity
        messenger(
            MESSAGES.SCREENING,
            request=self.request,
            user=self.request.user,
            submission=self.object,
            related=str(old.screening_status),
        )
        return response


@method_decorator(staff_required, name='dispatch')
class UpdateLeadView(DelegatedViewMixin, UpdateView):
    model = ApplicationSubmission
    form_class = UpdateSubmissionLeadForm
    context_name = 'lead_form'

    def form_valid(self, form):
        # Fetch the old lead from the database
        old = copy(self.get_object())
        response = super().form_valid(form)
        messenger(
            MESSAGES.UPDATE_LEAD,
            request=self.request,
            user=self.request.user,
            submission=form.instance,
            related=old.lead,
        )
        return response


@method_decorator(staff_required, name='dispatch')
class UpdateReviewersView(DelegatedViewMixin, UpdateView):
    model = ApplicationSubmission
    form_class = UpdateReviewersForm
    context_name = 'reviewer_form'

    def form_valid(self, form):
        response = super().form_valid(form)
        if len(form.cleaned_data.values()) != len(set(form.cleaned_data.values())):  # If any of the users match
            error_message = _('Users cannot be assigned to multiple roles.')
            messages.error(self.request, mark_safe(error_message + form.errors.as_ul()))
            form.add_error(None, error_message)
            return self.form_invalid(form)

        # Loop through cleaned_data and save reviewers by role type to submission
        for key, value in form.cleaned_data.items():
            role_pk = key[key.rindex("_") + 1:]
            role = ReviewerRole.objects.get(pk=role_pk)
            # Create the reviewer/role association to submission if it doesn't exist
            submission_reviewer, c = ApplicationSubmissionReviewer.objects.get_or_create(
                submission=form.instance, reviewer=value, reviewer_role=role)
            # Delete any reviewer/role associations that existed previously
            ApplicationSubmissionReviewer.objects.filter(
                Q(submission=form.instance),
                ~Q(reviewer=value),
                Q(reviewer_role=role)).delete()

        """
        old_reviewers = set(self.get_object().reviewers.all())
        new_reviewers = set(form.instance.reviewers.all())

        added = new_reviewers - old_reviewers
        removed = old_reviewers - new_reviewers

        messenger(
            MESSAGES.REVIEWERS_UPDATED,
            request=self.request,
            user=self.request.user,
            submission=self.kwargs['submission'],
            added=added,
            removed=removed,
        )
        """

        return response


class AdminSubmissionDetailView(ReviewContextMixin, ActivityContextMixin, DelegateableView, DetailView):
    template_name_suffix = '_admin_detail'
    model = ApplicationSubmission
    form_views = [
        ProgressSubmissionView,
        ScreeningSubmissionView,
        CommentFormView,
        UpdateLeadView,
        UpdateReviewersView,
    ]

    def dispatch(self, request, *args, **kwargs):
        submission = self.get_object()
        redirect = SubmissionSealedView.should_redirect(request, submission)
        return redirect or super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        other_submissions = self.model.objects.filter(user=self.object.user).current().exclude(id=self.object.id)
        objects_with_icons = ReviewerRole.objects.all().order_by('order')
        if self.object.next:
            other_submissions = other_submissions.exclude(id=self.object.next.id)

        public_page = self.object.get_from_parent('detail')()

        return super().get_context_data(
            other_submissions=other_submissions,
            public_page=public_page,
            objects_with_icons=objects_with_icons,
            **kwargs,
        )


@method_decorator(staff_required, 'dispatch')
class SubmissionSealedView(DetailView):
    template_name = 'funds/submission_sealed.html'
    model = ApplicationSubmission

    def get(self, request, *args, **kwargs):
        submission = self.get_object()
        if not self.round_is_sealed(submission):
            return self.redirect_detail(submission)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        submission = self.get_object()
        if self.can_view_sealed(request.user):
            self.peeked(submission)
        return self.redirect_detail(submission)

    def redirect_detail(self, submission):
        return HttpResponseRedirect(reverse_lazy('funds:submissions:detail', args=(submission.id,)))

    def peeked(self, submission):
        messenger(
            MESSAGES.OPENED_SEALED,
            request=self.request,
            user=self.request.user,
            submission=submission,
        )
        self.request.session.setdefault('peeked', {})[str(submission.id)] = True
        # Dictionary updates do not trigger session saves. Force update
        self.request.session.modified = True

    def can_view_sealed(self, user):
        return user.is_superuser

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            can_view_sealed=self.can_view_sealed(self.request.user),
            **kwargs,
        )

    @classmethod
    def round_is_sealed(cls, submission):
        try:
            return submission.round.specific.is_sealed
        except AttributeError:
            # Its a lab - cant be sealed
            return False

    @classmethod
    def has_peeked(cls, request, submission):
        return str(submission.id) in request.session.get('peeked', {})

    @classmethod
    def should_redirect(cls, request, submission):
        if cls.round_is_sealed(submission) and not cls.has_peeked(request, submission):
            return HttpResponseRedirect(reverse_lazy('funds:submissions:sealed', args=(submission.id,)))


class ApplicantSubmissionDetailView(ActivityContextMixin, DelegateableView, DetailView):
    model = ApplicationSubmission
    form_views = [CommentFormView]

    def get_object(self):
        return super().get_object().from_draft()

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().user != request.user:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SubmissionDetailView(ViewDispatcher):
    admin_view = AdminSubmissionDetailView
    applicant_view = ApplicantSubmissionDetailView

    def admin_check(self, request):
        if request.user.is_reviewer:
            return True
        return super().admin_check(request)


class BaseSubmissionEditView(UpdateView):
    """
    Converts the data held on the submission into an editable format and knows how to save
    that back to the object. Shortcuts the normal update view save approach
    """
    model = ApplicationSubmission

    def dispatch(self, request, *args, **kwargs):
        if not self.get_object().phase.permissions.can_edit(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def buttons(self):
        yield ('save', 'white', 'Save Draft')
        yield ('submit', 'primary', 'Submit')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        instance = kwargs.pop('instance').from_draft()
        kwargs['initial'] = instance.raw_data
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(buttons=self.buttons(), **kwargs)

    def get_form_class(self):
        return self.object.get_form_class()


@method_decorator(staff_required, name='dispatch')
class AdminSubmissionEditView(BaseSubmissionEditView):
    def form_valid(self, form):
        self.object.new_data(form.cleaned_data)

        if 'save' in self.request.POST:
            self.object.create_revision(draft=True, by=self.request.user)
            return self.form_invalid(form)

        if 'submit' in self.request.POST:
            revision = self.object.create_revision(by=self.request.user)
            if revision:
                messenger(
                    MESSAGES.EDIT,
                    request=self.request,
                    user=self.request.user,
                    submission=self.object,
                    related=revision,
                )

        return HttpResponseRedirect(self.get_success_url())


@method_decorator(login_required, name='dispatch')
class ApplicantSubmissionEditView(BaseSubmissionEditView):
    def dispatch(self, request, *args, **kwargs):
        if request.user != self.get_object().user:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    @property
    def transitions(self):
        transitions = self.object.get_available_user_status_transitions(self.request.user)
        return {
            transition.name: transition
            for transition in transitions
        }

    def form_valid(self, form):
        self.object.new_data(form.cleaned_data)

        if 'save' in self.request.POST:
            self.object.create_revision(draft=True, by=self.request.user)
            messages.success(self.request, _('Submission saved successfully'))
            return self.form_invalid(form)

        revision = self.object.create_revision(by=self.request.user)
        submitting_proposal = self.object.phase.name in STAGE_CHANGE_ACTIONS

        if submitting_proposal:
            messenger(
                MESSAGES.PROPOSAL_SUBMITTED,
                request=self.request,
                user=self.request.user,
                submission=self.object,
            )
        elif revision:
            messenger(
                MESSAGES.APPLICANT_EDIT,
                request=self.request,
                user=self.request.user,
                submission=self.object,
                related=revision,
            )

        action = set(self.request.POST.keys()) & set(self.transitions.keys())
        transition = self.transitions[action.pop()]

        self.object.perform_transition(
            transition.target,
            self.request.user,
            request=self.request,
            notify=not (revision or submitting_proposal),  # Use the other notification
        )

        return HttpResponseRedirect(self.get_success_url())


class SubmissionEditView(ViewDispatcher):
    admin_view = AdminSubmissionEditView
    applicant_view = ApplicantSubmissionEditView


@method_decorator(staff_required, name='dispatch')
class RevisionListView(ListView):
    model = ApplicationRevision

    def get_queryset(self):
        self.submission = get_object_or_404(ApplicationSubmission, id=self.kwargs['submission_pk'])
        self.queryset = self.model.objects.filter(
            submission=self.submission,
        ).exclude(
            draft__isnull=False,
            live__isnull=True,
        )
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            submission=self.submission,
            **kwargs,
        )


@method_decorator(staff_required, name='dispatch')
class RevisionCompareView(DetailView):
    model = ApplicationSubmission
    template_name = 'funds/revisions_compare.html'
    pk_url_kwarg = 'submission_pk'

    def compare_revisions(self, from_data, to_data):
        self.object.form_data = from_data.form_data
        from_fields = self.object.render_answers()
        from_required = self.render_required()

        self.object.form_data = to_data.form_data
        to_fields = self.object.render_answers()
        to_required = self.render_required()

        # Compare all the required fields
        diffed_required = [
            compare(*fields, should_bleach=False)
            for fields in zip(from_required, to_required)
        ]
        for field, diff in zip(self.object.named_blocks, diffed_required):
            setattr(self.object, 'get_{}_display'.format(field), diff)

        # Compare all the answers
        diffed_answers = [
            compare(*fields, should_bleach=False)
            for fields in zip(from_fields, to_fields)
        ]

        self.object.output_answers = mark_safe(''.join(diffed_answers))

    def render_required(self):
        return [
            getattr(self.object, 'get_{}_display'.format(field))()
            for field in self.object.named_blocks
        ]

    def get_context_data(self, **kwargs):
        from_revision = self.object.revisions.get(id=self.kwargs['from'])
        to_revision = self.object.revisions.get(id=self.kwargs['to'])
        self.compare_revisions(from_revision, to_revision)
        return super().get_context_data(**kwargs)


@method_decorator(staff_required, name='dispatch')
class RoundListView(SingleTableMixin, FilterView):
    template_name = 'funds/rounds.html'
    table_class = RoundsTable
    filterset_class = RoundsFilter

    def get_queryset(self):
        return RoundsAndLabs.objects.with_progress()
