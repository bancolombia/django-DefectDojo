import uuid
import logging
from enum import Enum

from django.db import transaction
from django.db.models import F
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from celery import chord
from celery import current_app

from celery.utils.log import get_task_logger

from dojo.celery import app
from dojo.models import Product, Dojo_Group
from dojo.group.queries import get_group_members_for_group
from dojo.notifications.helper import create_notification
from dojo.api_v2.risk_posture.helper import get_product_risk_posture as get_product_security_posture
from dojo.engine_participation.models import HCParticipation, HCParticipationLog

logger = get_task_logger(__name__)

ELIGIBLE_CRITICALITIES = ("very high", "high")
ACTIVE_HC_REQUEST_STATUSES = ("Pending", "Reviewed")
HC_BMC_APPLICATION_CLASSID_MARKER = "CLASSID: BMC_APPLICATION"
HC_STATUS_TRANSITIONS = {
    "Reviewed": {"Pending"},
    "Approved": {"Reviewed"},
    "Rejected": {"Pending", "Reviewed"},
}


class HCConstants(Enum):
    REVIEWERS_GROUP = settings.HC_REVIEWER_GROUP_NAME
    APPROVERS_GROUP = settings.HC_APPROVER_GROUP_NAME


class InvalidHCParticipationTransition(Exception):
    """Raised when a workflow action is attempted from an invalid state."""


def get_hc_reviewers_members():
    reviewer_group = Dojo_Group.objects.filter(
        name=HCConstants.REVIEWERS_GROUP.value
    ).first()
    
    if not reviewer_group:
        return []
    
    reviewer_members = get_group_members_for_group(reviewer_group)
    return [member.user.username for member in reviewer_members if member]


def get_hc_approvers_members():
    approvers_group = Dojo_Group.objects.filter(
        name=HCConstants.APPROVERS_GROUP.value
    ).first()
    
    if not approvers_group:
        return []
    
    approvers_members = get_group_members_for_group(approvers_group)
    return [member.user.username for member in approvers_members if member]


def has_valid_comments(hc_participation, user) -> bool:
    if user.is_superuser:
        return True
    
    for comment in hc_participation.discussions.all():
        if comment.author == user:
            return True
    return False


def _validate_hc_status_transition(current_status: str, target_status: str) -> None:
    allowed_statuses = HC_STATUS_TRANSITIONS.get(target_status, set())
    if current_status not in allowed_statuses:
        allowed_labels = ", ".join(sorted(allowed_statuses)) or "none"
        raise InvalidHCParticipationTransition(
            f"Cannot change HC request from {current_status} to {target_status}. "
            f"Allowed previous statuses: {allowed_labels}."
        )


def evaluate_product_for_hc(product: Product) -> dict:
    result = {
        "product_id": product.id,
        "product_name": product.name,
        "business_criticality": product.business_criticality,
        "was_in_hacking_continuous": False,
        "recommendation": None,
        "reason": None,
        "security_posture": None,
    }
    
    security_posture = get_product_security_posture(product, None)
    result["security_posture"] = {
        "is_in_hacking_continuos": security_posture.get("is_in_hacking_continuos", False),
        "counter_active_findings": security_posture.get("counter_active_findings", 0),
        "counter_total_findings": security_posture.get("counter_total_findings", 0),
        "adoption_devsecops": security_posture.get("adoption_devsecops", []),
        "result": security_posture.get("result", 0),
        "status": security_posture.get("status", "UNKNOWN"),
    }
    
    result["was_in_hacking_continuous"] = security_posture.get("is_in_hacking_continuos", False)
    
    criticality = product.business_criticality
    if not criticality or criticality.lower() not in ELIGIBLE_CRITICALITIES:
        result["recommendation"] = HCParticipation.RECOMMENDATION_CHOICES[2][0]  # not_eligible
        result["reason"] = (
            f"Business criticality '{criticality or 'Not defined'}' "
            f"is not eligible. Only High/Very High are eligible."
        )
        return result
    
    if security_posture.get("is_in_hacking_continuos", False):
        result["recommendation"] = HCParticipation.RECOMMENDATION_CHOICES[1][0]  # already_in_hc
        result["reason"] = "Product is already in Hacking Continuous. Documented, no postulation required."
        return result
    
    result["recommendation"] = HCParticipation.RECOMMENDATION_CHOICES[0][0]  # postulated
    result["reason"] = (
        f"Product eligible for Hacking Continuous postulation. "
        f"Criticality: {criticality}. Requires review and approval."
    )
    
    return result


def _process_single_product(product: Product, batch_id: uuid.UUID, user) -> dict:
    try:
        evaluation_result = evaluate_product_for_hc(product)
        
        hc_request = HCParticipation(
            product=product,
            recommendation=evaluation_result["recommendation"],
            business_criticality=evaluation_result["business_criticality"],
            was_in_hacking_continuous=evaluation_result["was_in_hacking_continuous"],
            security_posture_data=evaluation_result["security_posture"],
            reason=evaluation_result["reason"],
            status="Pending",
            created_by=user,
            batch_id=batch_id,
        )
        
        return {
            "evaluation_result": evaluation_result,
            "hc_request": hc_request,
        }
    except Exception as e:
        logger.exception(f"Error evaluating product {product.id}: {e}")
        return {
            "evaluation_result": {
                "product_id": product.id,
                "product_name": product.name,
                "recommendation": "error",
                "reason": str(e),
            },
            "hc_request": None,
        }


def _notify_reviewers_of_new_requests(requests=None, batch_id=None, product_names=None, total_requests=None):
    reviewers = get_hc_reviewers_members()
    
    if not reviewers:
        logger.warning("No reviewers found for HC participation notifications")
        return
    
    if requests is not None:
        names = [req.product.name for req in requests[:5]]
        total = len(requests)
    else:
        names = (product_names or [])[:5]
        total = total_requests or 0

    more_text = f" and {total - 5} more" if total > 5 else ""
    
    create_notification(
        event="hc_participation_request",
        subject=f"🎯 {total} new Hacking Continuous requests",
        title=f"New Hacking Continuous participation requests",
        description=(
            f"{total} new HC participation requests have been generated "
            f"for products: {', '.join(names)}{more_text}. "
            f"Batch ID: {batch_id}"
        ),
        url=reverse("hc_participations"),
        recipients=reviewers,
        icon="bullseye",
        color_icon="#17a2b8",
    )


def mark_hc_participation_reviewed(hc_participation, user):
    with transaction.atomic():
        locked_hc_participation = HCParticipation.objects.select_for_update().get(pk=hc_participation.pk)
        _validate_hc_status_transition(locked_hc_participation.status, "Reviewed")

        previous_status = locked_hc_participation.status
        current_time = timezone.now()

        locked_hc_participation.status = "Reviewed"
        locked_hc_participation.reviewed_at = current_time
        locked_hc_participation.reviewed_by = user
        locked_hc_participation.status_updated_at = current_time
        locked_hc_participation.status_updated_by = user
        locked_hc_participation.save()

        HCParticipationLog.objects.create(
            hc_participation=locked_hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Reviewed",
            notes="Request marked as reviewed",
        )

    return locked_hc_participation


def approve_hc_participation(hc_participation, user):
 
    with transaction.atomic():
        hc_participation = HCParticipation.objects.select_for_update().get(pk=hc_participation.pk)
        _validate_hc_status_transition(hc_participation.status, "Approved")

        previous_status = hc_participation.status
        current_time = timezone.now()

        hc_participation.status = "Approved"
        hc_participation.final_status = "Approved"
        hc_participation.approved_at = current_time
        hc_participation.approved_by = user
        hc_participation.status_updated_at = current_time
        hc_participation.status_updated_by = user
        hc_participation.save()

        HCParticipationLog.objects.create(
            hc_participation=hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Approved",
            notes="Request approved for Hacking Continuous participation",
        )

    if hc_participation.created_by:
        create_notification(
            event="hc_participation_approved",
            subject=f"✅ HC Request approved - {hc_participation.product.name}",
            title=f"HC Request approved for {hc_participation.product.name}",
            description=f"The Hacking Continuous participation request for product {hc_participation.product.name} has been approved.",
            url=reverse("hc_participation", args=[str(hc_participation.pk)]),
            recipients=[hc_participation.created_by.username],
            icon="check-circle",
            color_icon="#28a745",
        )

    return hc_participation


def reject_hc_participation(hc_participation, user):
    with transaction.atomic():
        hc_participation = HCParticipation.objects.select_for_update().get(pk=hc_participation.pk)
        _validate_hc_status_transition(hc_participation.status, "Rejected")

        previous_status = hc_participation.status
        current_time = timezone.now()

        hc_participation.status = "Rejected"
        hc_participation.final_status = "Rejected"
        hc_participation.rejected_by = user
        hc_participation.status_updated_at = current_time
        hc_participation.status_updated_by = user

        if not hc_participation.reviewed_at:
            hc_participation.reviewed_at = current_time
            hc_participation.reviewed_by = user

        hc_participation.save()

        HCParticipationLog.objects.create(
            hc_participation=hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Rejected",
            notes="Request rejected",
        )

    if hc_participation.created_by:
        create_notification(
            event="hc_participation_rejected",
            subject=f"❌ HC Request rejected - {hc_participation.product.name}",
            title=f"HC Request rejected for {hc_participation.product.name}",
            description=f"The Hacking Continuous participation request for product {hc_participation.product.name} has been rejected.",
            url=reverse("hc_participation", args=[str(hc_participation.pk)]),
            recipients=[hc_participation.created_by.username],
            icon="times-circle",
            color_icon="#dc3545",
        )

    return hc_participation


def get_latest_hc_evaluation_for_product(product_id: int) -> dict:
    try:
        evaluation = HCParticipation.objects.filter(
            product_id=product_id
        ).order_by("-create_date").first()
        
        if not evaluation:
            return None
        
        return {
            "evaluation_id": str(evaluation.uuid),
            "evaluation_date": evaluation.create_date.isoformat(),
            "recommendation": evaluation.recommendation,
            "status": evaluation.status,
            "final_status": evaluation.final_status,
            "business_criticality": evaluation.business_criticality,
            "was_in_hacking_continuous": evaluation.was_in_hacking_continuous,
            "reason": evaluation.reason,
            "reviewed_by": evaluation.reviewed_by.username if evaluation.reviewed_by else None,
            "approved_by": evaluation.approved_by.username if evaluation.approved_by else None,
        }
    except Exception as e:
        logger.exception(f"Error getting latest HC evaluation for product {product_id}: {e}")
        return None


_CHUNK_SIZE = 25


def _is_hc_evaluation_task_live(task_id: str) -> bool:
    if not task_id:
        return False

    try:
        inspector = current_app.control.inspect(timeout=1)
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
    except Exception:
        # Fail-open: if broker/inspect is temporarily unavailable, avoid false negatives.
        return True

    for worker_tasks in active.values():
        if any(task.get("id") == task_id for task in worker_tasks):
            return True

    for worker_tasks in reserved.values():
        if any(task.get("id") == task_id for task in worker_tasks):
            return True

    for worker_tasks in scheduled.values():
        for task in worker_tasks:
            request = task.get("request") or {}
            if request.get("id") == task_id:
                return True

    return False


_ORPHAN_GRACE_PERIOD_SECONDS = 120


def finalize_orphan_hc_evaluation_run(run, reason: str | None = None) -> bool:
    from dojo.engine_participation.models import HCEvaluationRun

    if run.status not in (HCEvaluationRun.STATUS_PENDING, HCEvaluationRun.STATUS_RUNNING):
        return False

    age_seconds = (timezone.now() - run.create_date).total_seconds()
    if age_seconds < _ORPHAN_GRACE_PERIOD_SECONDS:
        return False

    if run.celery_task_id and _is_hc_evaluation_task_live(run.celery_task_id):
        return False

    run.status = HCEvaluationRun.STATUS_FAILED
    run.finished_at = timezone.now()
    if not run.error_message:
        run.error_message = reason or (
            "Run was auto-finalized because the Celery task is no longer live "
            "(worker restart/termination detected)."
        )
    run.save(update_fields=["status", "finished_at", "error_message"])
    return True


def reconcile_orphan_hc_evaluation_runs() -> int:
    from dojo.engine_participation.models import HCEvaluationRun

    finalized = 0
    candidates = HCEvaluationRun.objects.filter(
        status__in=[HCEvaluationRun.STATUS_PENDING, HCEvaluationRun.STATUS_RUNNING],
    ).order_by("-create_date")

    for run in candidates:
        if finalize_orphan_hc_evaluation_run(run):
            finalized += 1

    return finalized


def get_active_hc_evaluation_run():
    from dojo.engine_participation.models import HCEvaluationRun

    reconcile_orphan_hc_evaluation_runs()
    return HCEvaluationRun.objects.filter(
        status__in=[HCEvaluationRun.STATUS_PENDING, HCEvaluationRun.STATUS_RUNNING],
    ).order_by("-create_date").first()


def _build_empty_summary(total_products: int, candidates_count: int, skipped_by_classid: int) -> dict:
    return {
        "postulated": 0,
        "already_in_hc": 0,
        "not_eligible": 0,
        "errors": 0,
        "total_evaluated": 0,
        "requests_created": 0,
        "scope": {
            "total_products": total_products,
            "classid_candidates": candidates_count,
            "skipped_by_classid": skipped_by_classid,
        },
    }


@app.task(bind=True)
def run_hc_participation_evaluation_chunk_task(
    self,
    run_id: str,
    user_id: int | None,
    batch_id: str,
    product_ids: list[int],
):
    from django.contrib.auth import get_user_model
    from dojo.engine_participation.models import HCEvaluationRun

    User = get_user_model()
    user = User.objects.filter(id=user_id).first() if user_id else None
    batch_uuid = uuid.UUID(batch_id)

    products = list(Product.objects.select_related("prod_type").filter(id__in=product_ids))

    requests_to_create = []
    already_in_hc_requests = []

    summary = {
        "postulated": 0,
        "already_in_hc": 0,
        "not_eligible": 0,
        "errors": 0,
        "total_evaluated": len(products),
        "requests_created": 0,
        "sample_created_products": [],
    }

    for product in products:
        process_result = _process_single_product(product, batch_uuid, user)
        rec = process_result["evaluation_result"]["recommendation"]
        if rec == "postulated":
            summary["postulated"] += 1
            if process_result["hc_request"]:
                requests_to_create.append(process_result["hc_request"])
        elif rec == "already_in_hc":
            summary["already_in_hc"] += 1
            if process_result["hc_request"]:
                already_in_hc_requests.append(process_result["hc_request"])
        elif rec == "not_eligible":
            summary["not_eligible"] += 1
        else:
            summary["errors"] += 1

    created_requests = []
    requests_to_create.sort(key=lambda r: r.product_id)
    already_in_hc_requests.sort(key=lambda r: r.product_id)

    with transaction.atomic():
        for hc_request in requests_to_create:
            locked_product = Product.objects.select_for_update().get(pk=hc_request.product_id)
            existing = HCParticipation.objects.filter(
                product=locked_product,
                status__in=ACTIVE_HC_REQUEST_STATUSES,
            ).exists()
            if not existing:
                hc_request.product = locked_product
                hc_request.save()
                created_requests.append(hc_request)

        if already_in_hc_requests:
            HCParticipation.objects.bulk_create(already_in_hc_requests, batch_size=500)

    summary["requests_created"] = len(created_requests)
    summary["sample_created_products"] = [req.product.name for req in created_requests[:5]]

    HCEvaluationRun.objects.filter(id=run_id).update(processed_count=F("processed_count") + len(products))

    return summary


@app.task(bind=True)
def run_hc_participation_evaluation_finalize_task(
    self,
    chunk_summaries: list[dict],
    run_id: str,
    batch_id: str,
    total_products: int,
    candidates_count: int,
    skipped_by_classid: int,
):
    from dojo.engine_participation.models import HCEvaluationRun

    run = HCEvaluationRun.objects.get(id=run_id)

    aggregated = _build_empty_summary(total_products, candidates_count, skipped_by_classid)
    aggregated["batch_id"] = batch_id
    sample_created_products = []

    for chunk in chunk_summaries or []:
        aggregated["postulated"] += chunk.get("postulated", 0)
        aggregated["already_in_hc"] += chunk.get("already_in_hc", 0)
        aggregated["not_eligible"] += chunk.get("not_eligible", 0)
        aggregated["errors"] += chunk.get("errors", 0)
        aggregated["total_evaluated"] += chunk.get("total_evaluated", 0)
        aggregated["requests_created"] += chunk.get("requests_created", 0)
        sample_created_products.extend(chunk.get("sample_created_products", []))

    run.status = HCEvaluationRun.STATUS_COMPLETED
    run.finished_at = timezone.now()
    run.result_summary = aggregated
    run.processed_count = candidates_count
    run.save(update_fields=["status", "finished_at", "result_summary", "processed_count"])

    if aggregated["requests_created"] > 0:
        _notify_reviewers_of_new_requests(
            batch_id=batch_id,
            product_names=sample_created_products,
            total_requests=aggregated["requests_created"],
        )

    logger.info(
        "[HCEvaluationRun %s] Evaluation completed – %s evaluated, %s new postulation requests created.",
        run_id,
        aggregated["total_evaluated"],
        aggregated["requests_created"],
    )

    return aggregated


@app.task(bind=True)
def run_hc_participation_evaluation_task(self, run_id: str, user_id: int = None):
    from dojo.engine_participation.models import HCEvaluationRun

    run = HCEvaluationRun.objects.get(id=run_id)

    def _log(msg, level="INFO"):
        if level == "ERROR":
            logger.error("[HCEvaluationRun %s] %s", run_id, msg)
        elif level == "WARNING":
            logger.warning("[HCEvaluationRun %s] %s", run_id, msg)
        else:
            logger.info("[HCEvaluationRun %s] %s", run_id, msg)

    def _flush(extra_fields=None):
        fields = ["processed_count"]
        if extra_fields:
            for k, v in extra_fields.items():
                setattr(run, k, v)
                fields.append(k)
        run.save(update_fields=fields)

    try:
        run.status = HCEvaluationRun.STATUS_RUNNING
        run.started_at = timezone.now()
        run.celery_task_id = self.request.id
        run.processed_count = 0
        run.save(update_fields=["status", "started_at", "celery_task_id", "processed_count"])

        batch_id = uuid.uuid4()
        _log(f"Evaluation started. Batch ID: {batch_id}")

        total_products = Product.objects.count()
        products_qs = Product.objects.filter(
            description__icontains=HC_BMC_APPLICATION_CLASSID_MARKER,
        )
        candidates_count = products_qs.count()
        skipped_by_classid = max(total_products - candidates_count, 0)

        run.total_candidates = candidates_count
        run.save(update_fields=["total_candidates"])

        _log(
            f"Scope – total products: {total_products} | "
            f"CLASSID candidates: {candidates_count} | "
            f"skipped by CLASSID: {skipped_by_classid}"
        )

        product_ids = list(products_qs.values_list("id", flat=True))

        if not product_ids:
            HCParticipation.objects.filter(recommendation="already_in_hc").delete()
            _log("No products matched the CLASSID filter. Nothing to evaluate.")
            empty_summary = _build_empty_summary(total_products, 0, skipped_by_classid)
            _flush({
                "status": HCEvaluationRun.STATUS_COMPLETED,
                "finished_at": timezone.now(),
                "result_summary": empty_summary,
            })
            return empty_summary

        HCParticipation.objects.filter(recommendation="already_in_hc").delete()

        chunk_tasks = []
        for chunk_start in range(0, len(product_ids), _CHUNK_SIZE):
            chunk_ids = product_ids[chunk_start: chunk_start + _CHUNK_SIZE]
            chunk_tasks.append(
                run_hc_participation_evaluation_chunk_task.s(
                    run_id=run_id,
                    user_id=user_id,
                    batch_id=str(batch_id),
                    product_ids=chunk_ids,
                )
            )

        callback = run_hc_participation_evaluation_finalize_task.s(
            run_id=run_id,
            batch_id=str(batch_id),
            total_products=total_products,
            candidates_count=candidates_count,
            skipped_by_classid=skipped_by_classid,
        )
        async_result = chord(chunk_tasks)(callback)

        _log(
            f"Evaluation dispatched – {len(product_ids)} products in "
            f"{len(chunk_tasks)} chunk tasks. Callback task: {async_result.id}"
        )
        return {
            "status": "dispatched",
            "run_id": run_id,
            "batch_id": str(batch_id),
            "chunks": len(chunk_tasks),
            "candidates": len(product_ids),
            "callback_task_id": async_result.id,
        }

    except Exception as exc:
        logger.exception("[HCEvaluationRun %s] Task failed: %s", run_id, exc)
        _log(f"FATAL ERROR: {exc}", level="ERROR")
        _flush({
            "status": HCEvaluationRun.STATUS_FAILED,
            "finished_at": timezone.now(),
            "error_message": str(exc),
        })
        raise


