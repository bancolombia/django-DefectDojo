import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

from django.db import transaction
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

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

    if security_posture.get("is_in_hacking_continuos", False):
        result["recommendation"] = HCParticipation.RECOMMENDATION_CHOICES[1][0]  # already_in_hc
        result["reason"] = "Product is already in Hacking Continuous. Documented, no postulation required."
        return result
    
    criticality = product.business_criticality
    if not criticality or criticality.lower() not in ELIGIBLE_CRITICALITIES:
        result["recommendation"] = HCParticipation.RECOMMENDATION_CHOICES[2][0]  # not_eligible
        result["reason"] = (
            f"Business criticality '{criticality or 'Not defined'}' "
            f"is not eligible. Only High/Very High are eligible."
        )
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


def create_manual_hc_participation(product: Product, user):
    # Validation 1: existing postulation with Pending status for this product
    existing_pending = HCParticipation.objects.filter(
        product_id=product.id,
        status="Pending",
    ).first()

    if existing_pending:
        logger.info(
            "Product %s (%s) already has a Pending CP submission (uuid=%s). Skipping.",
            product.id, product.name, existing_pending.uuid,
        )
        return {
            "status": "skipped",
            "message": f"The product '{product.name}' is already submitted with Pending status.",
            "hc_participation": None,
        }

    # Validation 2: product is already in Continuous Pentesting according to risk posture
    security_posture = get_product_security_posture(product, None)
    if security_posture.get("is_in_hacking_continuos", False):
        logger.info(
            "Product %s (%s) is already in Continuous Pentesting. Skipping manual submission.",
            product.id, product.name,
        )
        return {
            "status": "skipped",
            "message": f"The product '{product.name}' is already in Continuous Pentesting.",
            "hc_participation": None,
        }

    # Create the record directly without passing through run_hc_participation_evaluation
    current_time = timezone.now()
    security_posture_data = {
        "is_in_hacking_continuos": False,
        "counter_active_findings": security_posture.get("counter_active_findings", 0),
        "counter_total_findings": security_posture.get("counter_total_findings", 0),
        "adoption_devsecops": security_posture.get("adoption_devsecops", []),
        "result": security_posture.get("result", 0),
        "status": security_posture.get("status", "UNKNOWN"),
    }

    hc_participation = HCParticipation.objects.create(
        product=product,
        recommendation="manual_postulated",
        business_criticality=product.business_criticality,
        was_in_hacking_continuous=False,
        security_posture_data=security_posture_data,
        reason=f"Product manually submitted for Continuous Pentesting by user {user.username}.",
        status="Pending",
        created_by=user,
        batch_id=uuid.uuid4(),
        status_updated_at=current_time,
        status_updated_by=user,
    )

    logger.info(
        "Product %s (%s) manually submitted by user %s (uuid=%s).",
        product.id, product.name, user.username, hc_participation.uuid,
    )

    _notify_reviewers_of_new_requests([hc_participation], hc_participation.batch_id)

    return {
        "status": "created",
        "message": f"The product '{product.name}' was successfully submitted for Continuous Pentesting.",
        "hc_participation": hc_participation,
    }


def run_hc_participation_evaluation(user=None, product: Product = None) -> dict:
    is_manual = product is not None
    batch_id = uuid.uuid4()

    if not is_manual:
        HCParticipation.objects.filter(recommendation="already_in_hc").delete()

    total_products = Product.objects.count()

    if is_manual:
        products_qs = Product.objects.select_related("prod_type").filter(pk=product.pk)
    else:
        products_qs = Product.objects.select_related("prod_type").filter(
            description__icontains=HC_BMC_APPLICATION_CLASSID_MARKER,
        )
    candidates_count = products_qs.count()
    skipped_by_classid = 0 if is_manual else max(total_products - candidates_count, 0)

    logger.info(
        "HC Participation Evaluation scope. Total products: %s, "
        "CLASSID candidates: %s, skipped by CLASSID filter: %s",
        total_products,
        candidates_count,
        skipped_by_classid,
    )
    
    products_list = list(products_qs)
    
    if not products_list:
        return {
            "batch_id": str(batch_id),
            "total_evaluated": 0,
            "scope": {
                "total_products": total_products,
                "classid_candidates": candidates_count,
                "skipped_by_classid": skipped_by_classid,
            },
            "summary": {
                "postulated": 0,
                "already_in_hc": 0,
                "not_eligible": 0,
                "errors": 0,
            },
            "requests_created": 0,
        }
    
    results = []
    requests_to_create = []
    already_in_hc_to_create = []
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        future_to_product = {
            executor.submit(_process_single_product, product, batch_id, user): product
            for product in products_list
        }
        
        for future in as_completed(future_to_product):
            process_result = future.result()
            results.append(process_result["evaluation_result"])
            
            if process_result["hc_request"]:
                rec = process_result["evaluation_result"]["recommendation"]
                if is_manual:
                    # Para postulación manual, siempre guardar como manual_postulated
                    requests_to_create.append(process_result["hc_request"])
                elif rec == "postulated":
                    requests_to_create.append(process_result["hc_request"])
                elif rec == "already_in_hc":
                    already_in_hc_to_create.append(process_result["hc_request"])
    
    created_requests = []
    requests_to_create.sort(key=lambda request: request.product_id)

    with transaction.atomic():
        # Persistir registros already_in_hc (documentación, sin flujo de aprobación)
        for hc_request in already_in_hc_to_create:
            hc_request.save()

        current_time = timezone.now()
        for hc_request in requests_to_create:
            if is_manual:
                hc_request.recommendation = "manual_postulated"
                hc_request.reason = (
                    f"Product was postulated manually to Hacking Continuous "
                    f"by user {user.username}."
                )
                hc_request.status_updated_at = current_time
                hc_request.status_updated_by = user
                hc_request.save()
                created_requests.append(hc_request)
            else:
                locked_product = Product.objects.select_for_update().get(pk=hc_request.product_id)
                existing = HCParticipation.objects.filter(
                    product=locked_product,
                    status__in=ACTIVE_HC_REQUEST_STATUSES,
                ).exists()

                if not existing:
                    hc_request.product = locked_product
                    hc_request.save()
                    created_requests.append(hc_request)
    
    if created_requests:
        _notify_reviewers_of_new_requests(created_requests, batch_id)
    
    summary = {
        "postulated": sum(1 for r in results if r["recommendation"] == "postulated"),
        "already_in_hc": sum(1 for r in results if r["recommendation"] == "already_in_hc"),
        "not_eligible": sum(1 for r in results if r["recommendation"] == "not_eligible"),
        "errors": sum(1 for r in results if r["recommendation"] == "error"),
    }
    
    logger.info(
        f"HC Participation Evaluation completed. Batch: {batch_id}, "
        f"Total products: {total_products}, "
        f"CLASSID candidates: {candidates_count}, "
        f"Skipped by CLASSID: {skipped_by_classid}, "
        f"Postulated: {summary['postulated']}, "
        f"Already in CP: {summary['already_in_hc']}, "
        f"Not eligible: {summary['not_eligible']}, "
        f"Requests created: {len(created_requests)}"
    )
    
    return {
        "batch_id": str(batch_id),
        "total_evaluated": len(results),
        "scope": {
            "total_products": total_products,
            "classid_candidates": candidates_count,
            "skipped_by_classid": skipped_by_classid,
        },
        "summary": summary,
        "requests_created": len(created_requests),
        "results": results,
    }


def _notify_reviewers_of_new_requests(requests, batch_id):
    reviewers = get_hc_reviewers_members()
    
    if not reviewers:
        logger.warning("No reviewers found for CP submission notifications")
        return
    
    product_names = [req.product.name for req in requests[:5]]
    more_text = f" and {len(requests) - 5} more" if len(requests) > 5 else ""
    
    create_notification(
        event="hc_participation_request",
        subject=f"🎯 {len(requests)} new Continuous Pentesting submissions",
        title=f"New Continuous Pentesting submission requests",
        description=(
            f"{len(requests)} new CP submission requests have been generated "
            f"for products: {', '.join(product_names)}{more_text}. "
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
            subject=f"✅ CP Request approved - {hc_participation.product.name}",
            title=f"Continuous Pentesting Request approved for {hc_participation.product.name}",
            description=f"The Continuous Pentesting submission request for product {hc_participation.product.name} has been approved.",
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
            subject=f"❌ CP Request rejected - {hc_participation.product.name}",
            title=f"Continuous Pentesting Request rejected for {hc_participation.product.name}",
            description=f"The Continuous Pentesting submission request for product {hc_participation.product.name} has been rejected.",
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


@app.task
def run_monthly_hc_evaluation():
    logger.info("Starting monthly HC participation evaluation...")
    
    try:
        result = run_hc_participation_evaluation()
        
        logger.info(
            f"Monthly HC evaluation completed. "
            f"Total evaluated: {result['total_evaluated']}, "
            f"Requests created: {result['requests_created']}"
        )
        
        return result
        
    except Exception as e:
        logger.exception(f"Error in monthly HC evaluation: {e}")
        raise


def get_latest_products_already_in_hc():
    return (
        HCParticipation.objects
        .filter(recommendation="already_in_hc")
        .select_related("product", "product__prod_type")
        .order_by("product_id", "-create_date")
        .distinct("product_id")
    )


