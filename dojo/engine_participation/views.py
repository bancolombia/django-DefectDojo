from django.contrib import messages
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST, require_http_methods

from dojo.utils import get_page_items, add_breadcrumb, Product_Tab
from dojo.templatetags.authorization_tags import is_in_group
from dojo.models import Product
from dojo.engine_participation.models import (
    HCParticipation,
    HCParticipationDiscussion,
)
from dojo.engine_participation.filters import HCParticipationFilter
from dojo.engine_participation.forms import (
    HCConfirmIngressPostulationForm,
    HCManualPostulationForm,
    HCParticipationDiscussionForm,
)
from dojo.engine_participation.helpers import (
    HCConstants,
    InvalidHCParticipationTransition,
    approve_hc_participation,
    create_manual_hc_postulation,
    get_hc_participation_summary,
    get_manual_hc_postulation_eligibility_error,
    reject_hc_participation,
    has_valid_comments,
    get_hc_approvers_members,
    is_hc_request_preselected,
    mark_hc_participation_reviewed,
    run_hc_participation_evaluation,
    set_hc_request_preselection,
)
from dojo.notifications.helper import create_notification


def _redirect_to_next_or_hc_list(request: HttpRequest) -> HttpResponse:
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("hc_participations")


def hc_participations(request: HttpRequest) -> HttpResponse:
    hc_requests = HCParticipation.objects.select_related(
        "product",
        "product__prod_type",
        "created_by",
        "reviewed_by",
        "approved_by"
    ).all().order_by("-create_date")
    
    filtered = HCParticipationFilter(request.GET, queryset=hc_requests)
    postulated_qs = filtered.qs.filter(recommendation__in=("postulated", "postulated_manually"))
    already_in_hc_qs = filtered.qs.filter(recommendation="already_in_hc")

    postulated_requests = get_page_items(request, postulated_qs, 25, prefix="postulated_")
    already_in_hc_requests = get_page_items(request, already_in_hc_qs, 25, prefix="already_")

    for hc_request in postulated_requests.object_list:
        hc_request.is_preselected_for_hc = is_hc_request_preselected(hc_request)
    
    add_breadcrumb(
        title="HC Participation Requests",
        top_level=True,
        request=request
    )

    summary = get_hc_participation_summary()
    
    return render(request, "dojo/hc_participation/list.html", {
        "has_hc_requests": filtered.qs.exists(),
        "filtered": filtered,
        "name": "Hacking Continuous - Participation Requests",
        "postulated_requests": postulated_requests,
        "already_in_hc_requests": already_in_hc_requests,
        "can_run_hc_evaluation": request.user.is_staff or request.user.is_superuser,
        "can_preselect_hc": is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value),
        "hc_summary": summary,
    })


@require_POST
def preselect_hc_participation_request(request: HttpRequest, hcid: str) -> HttpResponse:
    if not is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value):
        raise PermissionDenied

    hc_participation = get_object_or_404(HCParticipation, pk=hcid)
    try:
        set_hc_request_preselection(hc_participation, True)
        messages.add_message(
            request,
            messages.SUCCESS,
            "Request pre-selected successfully.",
            extra_tags="alert-success"
        )
    except InvalidHCParticipationTransition as exc:
        messages.add_message(
            request,
            messages.ERROR,
            str(exc),
            extra_tags="alert-danger"
        )

    return _redirect_to_next_or_hc_list(request)


@require_POST
def remove_hc_preselection_request(request: HttpRequest, hcid: str) -> HttpResponse:
    if not is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value):
        raise PermissionDenied

    hc_participation = get_object_or_404(HCParticipation, pk=hcid)
    try:
        set_hc_request_preselection(hc_participation, False)
        messages.add_message(
            request,
            messages.SUCCESS,
            "Pre-selection removed successfully.",
            extra_tags="alert-success"
        )
    except InvalidHCParticipationTransition as exc:
        messages.add_message(
            request,
            messages.ERROR,
            str(exc),
            extra_tags="alert-danger"
        )

    return _redirect_to_next_or_hc_list(request)


def show_hc_participation(request: HttpRequest, hcid: str) -> HttpResponse:
    hc_participation = get_object_or_404(
        HCParticipation.objects.select_related(
            "product",
            "product__prod_type",
            "created_by",
            "reviewed_by",
            "approved_by",
            "rejected_by",
            "status_updated_by"
        ),
        pk=hcid
    )
    
    discussion_form = HCParticipationDiscussionForm()
    review_checklist_form = HCConfirmIngressPostulationForm()
    requires_review_checklist = (
        hc_participation.recommendation in ("postulated", "postulated_manually")
        and review_checklist_form.requires_selection
    )
    logs = hc_participation.logs.select_related("changed_by").all()
    discussions = hc_participation.discussions.select_related("author").all()
    security_posture_data = hc_participation.security_posture_data if isinstance(hc_participation.security_posture_data, dict) else {}
    risk_posture_api_url = f"{reverse('product_risk_posture')}?product_id={hc_participation.product.id}"
    risk_posture_view_url = security_posture_data.get("product_risk_posture_url") or f"{reverse('product_risk_posture_view')}?product_id={hc_participation.product.id}"
    
    add_breadcrumb(
        title=f"HC - {hc_participation.product.name}",
        top_level=False,
        request=request
    )
    
    return render(request, "dojo/hc_participation/show.html", {
        "hc_participation": hc_participation,
        "discussion_form": discussion_form,
        "review_checklist_form": review_checklist_form,
        "requires_review_checklist": requires_review_checklist,
        "logs": logs,
        "discussions": discussions,
        "security_posture_data": security_posture_data,
        "risk_posture_api_url": risk_posture_api_url,
        "risk_posture_view_url": risk_posture_view_url,
        "can_review_hc_participation": is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value),
        "can_approve_hc_participation": is_in_group(request.user, HCConstants.APPROVERS_GROUP.value),
        "can_reject_hc_participation": (
            is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value)
            or is_in_group(request.user, HCConstants.APPROVERS_GROUP.value)
        ),
        "name": f"HC Request | {hc_participation.product.name}",
    })


@require_POST
def add_hc_discussion(request: HttpRequest, hcid: str) -> HttpResponse:
    hc_participation = get_object_or_404(HCParticipation, pk=hcid)

    form = HCParticipationDiscussionForm(request.POST)
    if form.is_valid():
        discussion = form.save(commit=False)
        discussion.hc_participation = hc_participation
        discussion.author = request.user
        discussion.save()
        
        messages.add_message(
            request,
            messages.SUCCESS,
            "Comment added.",
            extra_tags="alert-success"
        )
    
    return redirect("hc_participation", hcid=hcid)


@require_POST
def delete_hc_discussion(request: HttpRequest, hcid: str, did: int) -> HttpResponse:
    discussion = get_object_or_404(
        HCParticipationDiscussion,
        pk=did,
        hc_participation_id=hcid,
    )
    
    if discussion.author != request.user and not request.user.is_superuser:
        raise PermissionDenied
    
    discussion.delete()
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Comment deleted.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


@require_POST
def review_hc_participation(request: HttpRequest, hcid: str) -> HttpResponse:
    if not is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value):
        raise PermissionDenied
    
    hc_participation = get_object_or_404(HCParticipation, pk=hcid)
    confirmation_criteria = []

    if hc_participation.recommendation in ("postulated", "postulated_manually"):
        configured_criteria = list(getattr(settings, "HC_CONFIRM_INGRESS_POSTULATION_CRITERIA", []))
        raw_selected_criteria = [criterion.strip() for criterion in request.POST.getlist("criteria") if criterion.strip()]

        if configured_criteria and not raw_selected_criteria:
            messages.add_message(
                request,
                messages.ERROR,
                "You must confirm all ingress checklist criteria to mark as reviewed.",
                extra_tags="alert-danger"
            )
            return redirect("hc_participation", hcid=hcid)

        if configured_criteria:
            # Accept submitted values that match configured criteria after trim normalization.
            normalized_allowed = {criterion.strip(): criterion for criterion in configured_criteria}
            confirmation_criteria = [
                normalized_allowed[selected]
                for selected in raw_selected_criteria
                if selected in normalized_allowed
            ]

            if not confirmation_criteria:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "Selected checklist criteria are not valid.",
                    extra_tags="alert-danger"
                )
                return redirect("hc_participation", hcid=hcid)

            if len(set(confirmation_criteria)) != len(set(configured_criteria)):
                messages.add_message(
                    request,
                    messages.ERROR,
                    "You must confirm all ingress checklist criteria to mark as reviewed.",
                    extra_tags="alert-danger"
                )
                return redirect("hc_participation", hcid=hcid)
    
    if not has_valid_comments(hc_participation, request.user):
        messages.add_message(
            request,
            messages.ERROR,
            "You must add a comment before marking as reviewed.",
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)

    try:
        hc_participation = mark_hc_participation_reviewed(
            hc_participation,
            request.user,
            confirmation_criteria=confirmation_criteria,
        )
    except InvalidHCParticipationTransition as exc:
        messages.add_message(
            request,
            messages.ERROR,
            str(exc),
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)
    
    approvers = get_hc_approvers_members()
    
    create_notification(
        event="hc_participation_reviewed",
        subject=f"📋 HC Request reviewed - {hc_participation.product.name}",
        title=f"HC Request reviewed - {hc_participation.product.name}",
        description=f"The HC request for {hc_participation.product.name} has been reviewed and requires approval.",
        url=reverse("hc_participation", args=[str(hc_participation.pk)]),
        recipients=approvers,
        icon="clipboard-check",
        color_icon="#17a2b8",
        alert_only=True,
    )
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Request marked as reviewed.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


@require_POST
def approve_hc_participation_request(request: HttpRequest, hcid: str) -> HttpResponse:
    if not is_in_group(request.user, HCConstants.APPROVERS_GROUP.value):
        raise PermissionDenied
    
    hc_participation = get_object_or_404(HCParticipation, pk=hcid)
    
    if not has_valid_comments(hc_participation, request.user):
        messages.add_message(
            request,
            messages.ERROR,
            "You must add a comment before approving.",
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)

    try:
        approve_hc_participation(hc_participation, request.user)
    except InvalidHCParticipationTransition as exc:
        messages.add_message(
            request,
            messages.ERROR,
            str(exc),
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Removal approved successfully." if hc_participation.was_in_hacking_continuous else "Request approved successfully.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


@require_POST
def reject_hc_participation_request(request: HttpRequest, hcid: str) -> HttpResponse:
    if not is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value) and \
       not is_in_group(request.user, HCConstants.APPROVERS_GROUP.value):
        raise PermissionDenied
    
    hc_participation = get_object_or_404(HCParticipation, pk=hcid)
    
    if not has_valid_comments(hc_participation, request.user):
        messages.add_message(
            request,
            messages.ERROR,
            "You must add a comment before rejecting.",
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)

    try:
        reject_hc_participation(hc_participation, request.user)
    except InvalidHCParticipationTransition as exc:
        messages.add_message(
            request,
            messages.ERROR,
            str(exc),
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Product continues in HC." if hc_participation.was_in_hacking_continuous else "Request rejected.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


@require_POST
def run_hc_evaluation(request: HttpRequest) -> HttpResponse:
    if not request.user.is_superuser and not request.user.is_staff:
        raise PermissionDenied
    
    try:
        result = run_hc_participation_evaluation(user=request.user)
        
        messages.add_message(
            request,
            messages.SUCCESS,
            f"HC Evaluation completed. "
            f"Evaluated: {result['total_evaluated']}, "
            f"Postulated: {result['summary']['postulated']}, "
            f"Already in HC: {result['summary']['already_in_hc']}, "
            f"Not eligible: {result['summary']['not_eligible']}, "
            f"Requests created: {result['requests_created']}.",
            extra_tags="alert-success"
        )
    except Exception as e:
        messages.add_message(
            request,
            messages.ERROR,
            f"HC Evaluation failed: {str(e)}",
            extra_tags="alert-danger"
        )
    
    return redirect("hc_participations")


@require_http_methods(["GET", "POST"])
def create_manual_hc_postulation_request(request: HttpRequest, pid: int) -> HttpResponse:
    can_create_manual_postulation = (
        request.user.is_superuser
        or request.user.is_staff
        or is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value)
        or is_in_group(request.user, HCConstants.APPROVERS_GROUP.value)
    )
    if not can_create_manual_postulation:
        raise PermissionDenied

    product = get_object_or_404(Product, pk=pid)

    if request.method == "POST":
        form = HCManualPostulationForm(request.POST)
        if form.is_valid():
            _hc_request, error_message = create_manual_hc_postulation(
                product, request.user, form.cleaned_data["criteria"]
            )

            if error_message:
                messages.add_message(
                    request,
                    messages.INFO,
                    error_message,
                    extra_tags="alert-info"
                )
            else:
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    "Manual HC postulation created successfully.",
                    extra_tags="alert-success"
                )

            return redirect("view_product", pid=pid)
    else:
        eligibility_error = get_manual_hc_postulation_eligibility_error(product)
        if eligibility_error:
            messages.add_message(
                request,
                messages.INFO,
                eligibility_error,
                extra_tags="alert-info"
            )
            return redirect("view_product", pid=pid)

        form = HCManualPostulationForm()


    product_tab = Product_Tab(product, title=_("Manual HC Postulation"), tab="overview")
    add_breadcrumb(parent=product, title=_("Manual HC Postulation"), top_level=False, request=request)

    return render(request, "dojo/hc_participation/manual_postulation_form.html", {
        "product": product,
        "product_tab": product_tab,
        "form": form,
    })
