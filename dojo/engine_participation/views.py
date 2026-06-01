from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.utils import timezone

from dojo.utils import get_page_items, add_breadcrumb
from dojo.templatetags.authorization_tags import is_in_group
from dojo.models import Product
from dojo.engine_participation.models import (
    HCParticipation,
    HCParticipationDiscussion,
    HCEvaluationRun,
)
from dojo.engine_participation.filters import HCParticipationFilter
from dojo.engine_participation.forms import HCParticipationDiscussionForm
from dojo.engine_participation.helpers import (
    HCConstants,
    InvalidHCParticipationTransition,
    approve_hc_participation,
    reject_hc_participation,
    has_valid_comments,
    get_hc_approvers_members,
    mark_hc_participation_reviewed,
    run_hc_participation_evaluation_task,
)
from dojo.notifications.helper import create_notification


def hc_participations(request: HttpRequest) -> HttpResponse:
    hc_requests = HCParticipation.objects.select_related(
        "product",
        "product__prod_type",
        "created_by",
        "reviewed_by",
        "approved_by"
    ).filter(recommendation="postulated").order_by("-create_date")
    
    filtered = HCParticipationFilter(request.GET, queryset=hc_requests)
    paged_requests = get_page_items(request, filtered.qs, 25)
    
    # Get products already in HC directly from database
    products_already_in_hc_qs = HCParticipation.objects.select_related(
        "product",
        "product__prod_type"
    ).filter(recommendation="already_in_hc").order_by("-create_date")
    products_already_in_hc = get_page_items(
        request,
        products_already_in_hc_qs,
        25,
        prefix="already_in_hc_",
    )
    
    add_breadcrumb(
        title="HC Participation Requests",
        top_level=True,
        request=request
    )
    
    return render(request, "dojo/hc_participation/list.html", {
        "hc_requests": paged_requests,
        "filtered": filtered,
        "name": "Hacking Continuous - Participation Requests",
        "products_already_in_hc": products_already_in_hc,
    })


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
    logs = hc_participation.logs.select_related("changed_by").all()
    discussions = hc_participation.discussions.select_related("author").all()
    
    add_breadcrumb(
        title=f"HC - {hc_participation.product.name}",
        top_level=False,
        request=request
    )
    
    return render(request, "dojo/hc_participation/show.html", {
        "hc_participation": hc_participation,
        "discussion_form": discussion_form,
        "logs": logs,
        "discussions": discussions,
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
    
    if not has_valid_comments(hc_participation, request.user):
        messages.add_message(
            request,
            messages.ERROR,
            "You must add a comment before marking as reviewed.",
            extra_tags="alert-danger"
        )
        return redirect("hc_participation", hcid=hcid)

    try:
        hc_participation = mark_hc_participation_reviewed(hc_participation, request.user)
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
        "Request approved successfully.",
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
        "Request rejected.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


@require_POST
def run_hc_evaluation(request: HttpRequest) -> HttpResponse:
    if not request.user.is_superuser and not request.user.is_staff:
        raise PermissionDenied

    active_run = HCEvaluationRun.objects.filter(
        status__in=[HCEvaluationRun.STATUS_PENDING, HCEvaluationRun.STATUS_RUNNING]
    ).first()
    if active_run:
        messages.add_message(
            request,
            messages.WARNING,
            f"An evaluation is already running (ID: {active_run.id}). "
            "Please wait for it to finish before starting a new one.",
            extra_tags="alert-warning",
        )
        return redirect("hc_evaluation_run_status", run_id=str(active_run.id))

    run = HCEvaluationRun.objects.create(
        status=HCEvaluationRun.STATUS_PENDING,
        triggered_by=request.user,
    )

    task = run_hc_participation_evaluation_task.delay(
        run_id=str(run.id),
        user_id=request.user.id,
    )
    run.celery_task_id = task.id
    run.save(update_fields=["celery_task_id"])

    messages.add_message(
        request,
        messages.INFO,
        "HC Evaluation has been queued. You will be redirected to the status page.",
        extra_tags="alert-info",
    )
    return redirect("hc_evaluation_run_status", run_id=str(run.id))


@require_POST
def postulate_hc_product_manually(request: HttpRequest, pid: int) -> HttpResponse:
    can_postulate = (
        is_in_group(request.user, HCConstants.REVIEWERS_GROUP.value)
        or is_in_group(request.user, HCConstants.APPROVERS_GROUP.value)
        or is_in_group(request.user, "Reviewers_HC")
        or is_in_group(request.user, "Approvers_HC")
    )
    if not can_postulate:
        raise PermissionDenied

    product = get_object_or_404(Product, id=pid)

    already_pending = HCParticipation.objects.filter(
        product=product,
        recommendation="postulated",
        status="Pending",
    ).exists()
    if already_pending:
        messages.add_message(
            request,
            messages.WARNING,
            "This product already has a pending HC postulation request.",
            extra_tags="alert-warning",
        )
        return redirect("view_product", pid=product.id)

    HCParticipation.objects.create(
        product=product,
        recommendation="postulated",
        business_criticality=product.business_criticality,
        was_in_hacking_continuous=False,
        reason=(
            f"Manual postulation from product page by user {request.user.username}."
        ),
        status="Pending",
        created_by=request.user,
        status_updated_at=timezone.now(),
        status_updated_by=request.user,
    )

    messages.add_message(
        request,
        messages.SUCCESS,
        "Manual HC postulation request created successfully.",
        extra_tags="alert-success",
    )
    return redirect("view_product", pid=product.id)


def hc_evaluation_run_status(request: HttpRequest, run_id: str) -> HttpResponse:
    if not request.user.is_superuser and not request.user.is_staff:
        raise PermissionDenied

    run = get_object_or_404(HCEvaluationRun, id=run_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        run = HCEvaluationRun.objects.get(id=run_id)
        response = JsonResponse({
            "status": run.status,
            "progress_pct": run.progress_pct,
            "processed_count": run.processed_count,
            "total_candidates": run.total_candidates,
            "result_summary": run.result_summary,
            "error_message": run.error_message,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        })
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response

    recent_runs = HCEvaluationRun.objects.exclude(id=run.id).order_by("-create_date")[:10]

    add_breadcrumb(
        title="HC Participation Requests",
        top_level=True,
        url=reverse("hc_participations"),
        request=request,
    )
    add_breadcrumb(
        title="HC Evaluation Status",
        top_level=False,
        request=request,
    )
    return render(request, "dojo/hc_participation/evaluation_run_status.html", {
        "run": run,
        "recent_runs": recent_runs,
        "name": "HC Evaluation – Execution Status",
        "is_active": run.status in (HCEvaluationRun.STATUS_PENDING, HCEvaluationRun.STATUS_RUNNING),
    })
