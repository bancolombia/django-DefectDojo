import uuid
from enum import Enum
from urllib.parse import urlencode

import requests

from django.db import transaction
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from celery.utils.log import get_task_logger

from dojo.models import Product, Dojo_Group, Dojo_User
from dojo.group.queries import get_group_members_for_group
from dojo.notifications.helper import create_notification
from dojo.engine_participation.models import HCParticipation, HCParticipationLog

logger = get_task_logger(__name__)

ACTIVE_HC_REQUEST_STATUSES = ("Pending", "Reviewed")
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


def _get_hc_postulated_endpoint_url() -> str:
    endpoint_url = (getattr(settings, "HC_PARTICIPATION_POSTULATED_ENDPOINT", "") or "").strip()
    if not endpoint_url:
        raise ValueError(
            "HC participation endpoint is not configured. "
            "Set HC_PARTICIPATION_POSTULATED_ENDPOINT in settings/environment."
        )
    return endpoint_url


def _get_hc_already_in_hc_endpoint_url() -> str:
    return (getattr(settings, "HC_PARTICIPATION_ALREADY_IN_HC_ENDPOINT", "") or "").strip()


def _resolve_user_for_hc_evaluation(user):
    if user is not None:
        return user

    fallback_user = Dojo_User.objects.filter(is_superuser=True).order_by("id").first()
    if fallback_user:
        return fallback_user

    raise ValueError(
        "Unable to resolve an admin user token to call HC participation endpoint."
    )


def _get_user_token(user) -> str:
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


def _get_hc_postulated_auth_token(user) -> str:
    configured_token = (getattr(settings, "HC_PARTICIPATION_POSTULATED_AUTH_TOKEN", "") or "").strip()
    if configured_token:
        return configured_token
    return _get_user_token(user)


def _extract_rows(payload) -> list:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("postulated_products", "products", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def _build_product_risk_posture_url(product_id: int) -> str:
    query = urlencode({"product_id": product_id})
    return f"{reverse('product_risk_posture_view')}?{query}"


def _build_hc_common_body() -> dict:
    request_body = {
        "tags": list(getattr(settings, "HC_PARTICIPATION_POSTULATED_TAGS", [])),
        "days": int(getattr(settings, "HC_PARTICIPATION_DAYS", 300)),
        "classID": list(getattr(settings, "HC_PARTICIPATION_POSTULATED_CLASSID", [])),
        "businessCriticality": list(getattr(settings, "HC_PARTICIPATION_POSTULATED_BUSINESS_CRITICALITY", [])),
    }
    
    return request_body


def _build_hc_auth_headers(token_key: str) -> dict:
    return {
        "Authorization": f"Token {token_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _fetch_microservice(user, endpoint_url: str) -> list:
    if not endpoint_url:
        return []

    effective_user = _resolve_user_for_hc_evaluation(user)
    token_key = _get_hc_postulated_auth_token(effective_user)
    timeout_seconds = getattr(settings, "HC_PARTICIPATION_POSTULATED_TIMEOUT_SECONDS", 30)
    request_body = _build_hc_common_body()

    response = requests.post(
        endpoint_url,
        json=request_body,
        headers=_build_hc_auth_headers(token_key),
        timeout=timeout_seconds,
        verify=False,
    )
    response.raise_for_status()
    payload = response.json()

    return _extract_rows(payload)


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


def run_hc_participation_evaluation(user=None) -> dict:
    batch_id = uuid.uuid4()
    postulated_rows = _fetch_microservice(user, _get_hc_postulated_endpoint_url())
    already_in_hc_rows = _fetch_microservice(user, _get_hc_already_in_hc_endpoint_url())
    rows = [(row, "postulated") for row in postulated_rows] + [(row, "already_in_hc") for row in already_in_hc_rows]

    results = []
    requests_to_create = []

    product_ids = []
    for row, _default_recommendation in rows:
        if not isinstance(row, dict):
            continue
        product_id = row.get("id_product") or row.get("product_id") or row.get("id")
        if product_id is None:
            continue
        try:
            product_ids.append(int(product_id))
        except (TypeError, ValueError):
            logger.warning("Invalid id_product in HC microservice payload: %s", product_id)

    products_map = Product.objects.in_bulk(product_ids)

    for row, default_recommendation in rows:
        if not isinstance(row, dict):
            results.append(
                {
                    "product_id": None,
                    "product_name": None,
                    "recommendation": "error",
                    "reason": "Invalid row format returned by microservice.",
                }
            )
            continue

        product_id = row.get("id_product") or row.get("product_id") or row.get("id")
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            results.append(
                {
                    "product_id": product_id,
                    "product_name": row.get("product") or row.get("product_name") or row.get("name"),
                    "recommendation": "error",
                    "reason": "Invalid id_product in microservice payload.",
                }
            )
            continue

        product = products_map.get(product_id)
        if not product:
            results.append(
                {
                    "product_id": product_id,
                    "product_name": row.get("product") or row.get("product_name") or row.get("name"),
                    "recommendation": "error",
                    "reason": "Product not found in DefectDojo.",
                }
            )
            continue

        recommendation = row.get("recommendation") or default_recommendation
        if recommendation not in ("postulated", "already_in_hc", "not_eligible"):
            recommendation = "error"
        security_posture = {}
        security_posture.setdefault(
            "product_risk_posture_url",
            _build_product_risk_posture_url(product.id),
        )

        if recommendation == "already_in_hc":
            default_reason = "Product already in Hacking Continuous. Review required to continue."
        elif recommendation == "not_eligible":
            default_reason = "Product is not eligible for Hacking Continuous."
        else:
            default_reason = "Postulated to Hacking Continuous Test."

        evaluation_result = {
            "product_id": product.id,
            "product_name": product.name,
            "business_criticality": row.get("business_criticality") or product.business_criticality,
            "was_in_hacking_continuous": row.get("was_in_hacking_continuous", recommendation == "already_in_hc"),
            "recommendation": recommendation,
            "reason": row.get("reason") or default_reason,
            "security_posture": security_posture,
        }
        results.append(evaluation_result)

        if recommendation in ("postulated", "already_in_hc"):
            requests_to_create.append(
                HCParticipation(
                    product=product,
                    recommendation=recommendation,
                    business_criticality=evaluation_result["business_criticality"],
                    was_in_hacking_continuous=evaluation_result["was_in_hacking_continuous"],
                    security_posture_data=evaluation_result["security_posture"],
                    reason=evaluation_result["reason"],
                    status="Pending",
                    created_by=user,
                    batch_id=batch_id,
                )
            )
    
    created_requests = []
    requests_to_create.sort(key=lambda request: request.product_id)

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
        f"Rows received from microservice: {len(rows)}, "
        f"Postulated: {summary['postulated']}, "
        f"Already in HC: {summary['already_in_hc']}, "
        f"Not eligible: {summary['not_eligible']}, "
        f"Requests created: {len(created_requests)}"
    )
    
    return {
        "batch_id": str(batch_id),
        "total_evaluated": len(results),
        "scope": {
            "rows_from_microservice": len(rows),
            "rows_postulated_from_microservice": len(postulated_rows),
            "rows_already_in_hc_from_microservice": len(already_in_hc_rows),
        },
        "summary": summary,
        "requests_created": len(created_requests),
        "results": results,
    }


def _notify_reviewers_of_new_requests(requests, batch_id):
    reviewers = get_hc_reviewers_members()
    
    if not reviewers:
        logger.warning("No reviewers found for HC participation notifications")
        return
    
    product_names = [req.product.name for req in requests[:5]]
    more_text = f" and {len(requests) - 5} more" if len(requests) > 5 else ""
    
    create_notification(
        event="hc_participation_request",
        subject=f"🎯 {len(requests)} new Hacking Continuous requests",
        title=f"New Hacking Continuous participation requests",
        description=(
            f"{len(requests)} new HC participation requests have been generated "
            f"for products: {', '.join(product_names)}{more_text}. "
            f"Batch ID: {batch_id}"
        ),
        url=reverse("hc_participations"),
        recipients=reviewers,
        icon="bullseye",
        color_icon="#17a2b8",
    )


def is_product_in_hacking_continuous_from_requests(product) -> bool:
    latest_request = HCParticipation.objects.filter(
        product=product,
    ).order_by("-create_date").first()

    if not latest_request:
        return False

    if latest_request.recommendation in ("postulated", "postulated_manually"):
        return latest_request.status == "Approved"

    if latest_request.recommendation == "already_in_hc":
        return latest_request.status in ("Pending", "Reviewed", "Rejected")

    return False


def _get_product_class_id_from_description(product):
    description = (product.description or "")
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        upper_line = line.upper()
        if upper_line.startswith("CLASSID:"):
            return line.split(":", 1)[1].strip() or None
        if upper_line.startswith("CLASS ID:"):
            return line.split(":", 1)[1].strip() or None

    return None


def create_manual_hc_postulation(product, user):
    with transaction.atomic():
        locked_product = Product.objects.select_for_update().get(pk=product.pk)

        allowed_class_ids = list(getattr(settings, "HC_PARTICIPATION_POSTULATED_CLASSID", []))
        product_class_id = _get_product_class_id_from_description(locked_product)
        if allowed_class_ids and product_class_id not in allowed_class_ids:
            return None, (
                "This product class_id is not allowed for HC postulation. "
                f"Allowed class_id values: {', '.join(allowed_class_ids)}."
            )

        pending_postulation_exists = HCParticipation.objects.filter(
            product=locked_product,
            status="Pending",
        ).exists()
        if pending_postulation_exists:
            return None, "A pending HC postulation already exists for this product."

        if is_product_in_hacking_continuous_from_requests(locked_product):
            return None, "This product is already in Hacking Continuous."

        batch_id = uuid.uuid4()
        requested_by = getattr(user, "username", "System")
        hc_request = HCParticipation.objects.create(
            product=locked_product,
            recommendation="postulated_manually",
            business_criticality=locked_product.business_criticality,
            was_in_hacking_continuous=False,
            security_posture_data={
                "product_risk_posture_url": _build_product_risk_posture_url(locked_product.id),
            },
            reason=f"Manual postulation created from Product view by {requested_by}.",
            status="Pending",
            created_by=user,
            batch_id=batch_id,
        )

    _notify_reviewers_of_new_requests([hc_request], batch_id)
    return hc_request, None


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

        review_note = "Request marked as reviewed"
        if locked_hc_participation.was_in_hacking_continuous:
            review_note = "Request marked as reviewed for HC continuity decision"

        HCParticipationLog.objects.create(
            hc_participation=locked_hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Reviewed",
            notes=review_note,
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

        approval_note = "Request approved for Hacking Continuous participation"
        if hc_participation.was_in_hacking_continuous:
            approval_note = "Request approved for removal from Hacking Continuous"

        HCParticipationLog.objects.create(
            hc_participation=hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Approved",
            notes=approval_note,
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

        rejection_note = "Request rejected"
        if hc_participation.was_in_hacking_continuous:
            rejection_note = "Request rejected: product remains in Hacking Continuous"

        HCParticipationLog.objects.create(
            hc_participation=hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Rejected",
            notes=rejection_note,
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



