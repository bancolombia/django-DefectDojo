from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from dojo.celery import app
from dojo.engine_tools.helpers import Constants, get_note, get_reviewers_members, get_unique_ids_filter
from dojo.models import Finding
from dojo.notifications.helper import create_notification
from dojo.user.queries import get_user

from .models import CrossApprovalExclusion, CrossApprovalRequestLog


def _get_findings(exclusion):
    findings = Finding.objects.filter(
        get_unique_ids_filter(exclusion.vulnerability_id),
        active=True,
    ).prefetch_related("tags", "notes")
    if exclusion.image_names:
        image_filter = Q()
        for image_name in exclusion.image_names:
            image_filter |= Q(description__icontains=image_name)
        findings = findings.filter(image_filter)

    if exclusion.priority or exclusion.severity:
        priority = exclusion.priority.casefold()
        severity = exclusion.severity.casefold()
        findings = [
            finding for finding in findings
            if (
                priority and finding.priority_classification.casefold() == priority
            ) or (
                severity and finding.severity.casefold() == severity
            )
        ]
    return findings


@app.task
def apply_cross_approval_exclusion(exclusion_id):
    exclusion = CrossApprovalExclusion.objects.select_related("request").get(pk=exclusion_id)
    if (
        exclusion.request.status != "approved"
        or exclusion.expired_at
        or exclusion.expired_date < timezone.localdate()
    ):
        return

    system_user = get_user(settings.SYSTEM_USER)
    request_url = reverse("crossapproval_list")
    note = get_note(
        system_user,
        f"Finding added by cross-approval request {exclusion.request_id}: {request_url}",
    )
    for finding in _get_findings(exclusion):
        finding.tags.add("white_list", exclusion.request.type)
        finding.active = False
        finding.risk_status = Constants.ON_WHITELIST.value
        finding.notes.add(note)
        finding.save(update_fields=["active", "risk_status"])


def revert_cross_approval_exclusion(exclusion):
    system_user = get_user(settings.SYSTEM_USER)
    note = get_note(
        system_user,
        f"Finding removed from cross-approval request {exclusion.request_id}.",
    )
    findings = Finding.objects.filter(
        get_unique_ids_filter(exclusion.vulnerability_id),
        risk_status=Constants.ON_WHITELIST.value,
        tags__name=exclusion.request.type,
    ).prefetch_related("tags")
    for finding in findings:
        finding.tags.remove(exclusion.request.type)
        if "white_list" in finding.tags:
            finding.tags.remove("white_list")
        if not finding.is_mitigated:
            finding.active = True
        finding.risk_status = None
        finding.notes.add(note)
        finding.save(update_fields=["active", "risk_status"])


def expire_cross_approval_exclusion(exclusion, user):
    if exclusion.expired_at:
        return
    exclusion.expired_at = timezone.now()
    exclusion.save(update_fields=["expired_at"])
    revert_cross_approval_exclusion(exclusion)
    log_status_change(exclusion.request, user, "approved", "expired")


def reopen_cross_approval_exclusion(exclusion, user):
    if not exclusion.expired_at or exclusion.expired_date < timezone.localdate():
        return False
    exclusion.expired_at = None
    exclusion.save(update_fields=["expired_at"])
    log_status_change(exclusion.request, user, "expired", "approved")
    transaction.on_commit(
        lambda exclusion_id=exclusion.pk: apply_cross_approval_exclusion.delay(exclusion_id)
    )
    return True


@app.task
def revert_cross_approval_exclusion_task(exclusion_id):
    exclusion = CrossApprovalExclusion.objects.select_related("request").get(pk=exclusion_id)
    expire_cross_approval_exclusion(exclusion, get_user(settings.SYSTEM_USER))


def apply_request_exclusions(request):
    for exclusion in request.exclusions.all():
        transaction.on_commit(
            lambda exclusion_id=exclusion.pk: apply_cross_approval_exclusion.delay(exclusion_id)
        )


def expire_request_exclusions(request):
    for exclusion in request.exclusions.filter(
        expired_at__isnull=True,
        expired_date__lt=timezone.localdate(),
    ):
        expire_cross_approval_exclusion(exclusion, get_user(settings.SYSTEM_USER))


@app.task
def expire_cross_approval_exclusions():
    for exclusion in CrossApprovalExclusion.objects.filter(
        request__status="approved", expired_at__isnull=True, expired_date__lt=timezone.localdate()
    ):
        revert_cross_approval_exclusion_task.delay(exclusion.pk)


@app.task
def check_new_findings_to_cross_approval_exclusion_list():
    exclusions = CrossApprovalExclusion.objects.filter(
        request__status="approved",
        expired_at__isnull=True,
        expired_date__gte=timezone.localdate(),
    )
    for exclusion in exclusions:
        apply_cross_approval_exclusion.delay(exclusion.pk)


def log_status_change(request, user, previous_status, current_status):
    CrossApprovalRequestLog.objects.create(
        request=request,
        changed_by=user,
        previous_status=previous_status,
        current_status=current_status,
    )


def notify_request_status(request, event, title):
    recipients = {request.created_by.username}
    maintainers = get_reviewers_members()
    recipients.update(maintainers)
    create_notification(
        event=event,
        subject=title,
        title=title,
        description=title,
        url=reverse("crossapproval_list"),
        recipients=list(recipients),
    )