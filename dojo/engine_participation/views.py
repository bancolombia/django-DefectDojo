"""
Views for HC (Hacking Continuo) Participation module.

Provides UI for:
- Listing HC participation requests
- Running evaluations (admin only)
- Reviewing, approving, and rejecting requests
"""
from datetime import datetime

from django.contrib import messages
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from dojo.utils import get_page_items, add_breadcrumb
from dojo.templatetags.authorization_tags import is_in_group
from dojo.engine_participation.models import (
    HCParticipation,
    HCParticipationDiscussion,
    HCParticipationLog,
)
from dojo.engine_participation.filters import HCParticipationFilter
from dojo.engine_participation.forms import HCParticipationDiscussionForm
from dojo.engine_participation.helpers import (
    HCConstants,
    approve_hc_participation,
    reject_hc_participation,
    has_valid_comments,
    get_hc_approvers_members,
    run_hc_participation_evaluation,
)
from dojo.notifications.helper import create_notification


def hc_participations(request: HttpRequest) -> HttpResponse:
    """List all HC participation requests"""
    
    hc_requests = HCParticipation.objects.select_related(
        "product",
        "product__prod_type",
        "created_by",
        "reviewed_by",
        "approved_by"
    ).all().order_by("-create_date")
    
    filtered = HCParticipationFilter(request.GET, queryset=hc_requests)
    paged_requests = get_page_items(request, filtered.qs, 25)
    
    add_breadcrumb(
        title="HC Participation Requests",
        top_level=True,
        request=request
    )
    
    return render(request, "dojo/hc_participation/list.html", {
        "hc_requests": paged_requests,
        "filtered": filtered,
        "name": "Hacking Continuous - Participation Requests",
    })


def show_hc_participation(request: HttpRequest, hcid: str) -> HttpResponse:
    """Show HC participation request details"""
    
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
        "name": f"HC Request | {hc_participation.product.name}",
    })


def add_hc_discussion(request: HttpRequest, hcid: str) -> HttpResponse:
    """Add discussion/comment to HC participation request"""
    
    hc_participation = get_object_or_404(HCParticipation, pk=hcid)
    
    if request.method == "POST":
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


def delete_hc_discussion(request: HttpRequest, hcid: str, did: int) -> HttpResponse:
    """Delete a discussion from HC participation request"""
    
    discussion = get_object_or_404(HCParticipationDiscussion, pk=did)
    
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


def review_hc_participation(request: HttpRequest, hcid: str) -> HttpResponse:
    """Mark HC participation request as reviewed"""
    
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
    
    previous_status = hc_participation.status
    hc_participation.status = "Reviewed"
    hc_participation.reviewed_at = timezone.now()
    hc_participation.reviewed_by = request.user
    hc_participation.status_updated_at = timezone.now()
    hc_participation.status_updated_by = request.user
    hc_participation.save()
    
    HCParticipationLog.objects.create(
        hc_participation=hc_participation,
        changed_by=request.user,
        previous_status=previous_status,
        current_status="Reviewed",
        notes="Request marked as reviewed"
    )
    
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
    )
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Request marked as reviewed.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


def approve_hc_participation_request(request: HttpRequest, hcid: str) -> HttpResponse:
    """Approve HC participation request"""
    
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
    
    approve_hc_participation(hc_participation, request.user)
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Request approved successfully.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


def reject_hc_participation_request(request: HttpRequest, hcid: str) -> HttpResponse:
    """Reject HC participation request"""
    
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
    
    reject_hc_participation(hc_participation, request.user)
    
    messages.add_message(
        request,
        messages.SUCCESS,
        "Request rejected.",
        extra_tags="alert-success"
    )
    
    return redirect("hc_participation", hcid=hcid)


def run_hc_evaluation(request: HttpRequest) -> HttpResponse:
    """Manually trigger HC participation evaluation (admin only)."""
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
