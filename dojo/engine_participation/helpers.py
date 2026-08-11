import uuid
from enum import Enum
from urllib.parse import urlencode

import requests

from django.db import transaction
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from celery.utils.log import get_task_logger

from dojo.models import GeneralSettings, Product, Dojo_Group, Dojo_User
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
HC_APPROVAL_BAG_SIZE_KEY = "HACKING_CONTINUOUS_APPROVAL_BAG_SIZE"
HC_AVAILABLE_APPROVALS_DEFAULT = 0
HC_CONFIRM_INGRESS_POSTULATION_CRITERIA_KEY = "HC_CONFIRM_INGRESS_POSTULATION_CRITERIA"
HC_CONFIRM_INGRESS_POSTULATION_CRITERIA_DEFAULT = []
HC_MANUAL_POSTULATION_CRITERIA_KEY = "HC_MANUAL_POSTULATION_CRITERIA"
HC_MANUAL_POSTULATION_CRITERIA_DEFAULT = []
HC_PRESELECTED_FLAG_KEY = "is_preselected_for_hc"
HC_INGRESS_CONFIRMATION_CRITERIA_KEY = "ingress_confirmation_criteria_checked"


class HCConstants(Enum):
    REVIEWERS_GROUP = settings.HC_REVIEWER_GROUP_NAME
    APPROVERS_GROUP = settings.HC_APPROVER_GROUP_NAME


class InvalidHCParticipationTransition(Exception):
    """Raised when a workflow action is attempted from an invalid state."""


def _normalize_int(raw_value, default=0) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _clear_general_setting_cache(name_key: str) -> None:
    if getattr(settings, "USE_CACHE_REDIS", False):
        cache.delete(f"GENERAL_SETTINGS:{name_key}")


def get_hc_available_approvals() -> int:
    configured_value = GeneralSettings.get_value(
        HC_APPROVAL_BAG_SIZE_KEY,
        HC_AVAILABLE_APPROVALS_DEFAULT,
    )
    return _normalize_int(configured_value, default=HC_AVAILABLE_APPROVALS_DEFAULT)


def get_hc_confirm_ingress_postulation_criteria() -> list[str]:
    configured_value = GeneralSettings.get_value(
        HC_CONFIRM_INGRESS_POSTULATION_CRITERIA_KEY,
        HC_CONFIRM_INGRESS_POSTULATION_CRITERIA_DEFAULT,
    )

    if not configured_value:
        return []

    if isinstance(configured_value, str):
        configured_value = configured_value.split(",")

    if not isinstance(configured_value, list):
        return []

    return [criterion.strip() for criterion in configured_value if criterion and criterion.strip()]


def get_hc_manual_postulation_criteria() -> list[str]:
    configured_value = GeneralSettings.get_value(
        HC_MANUAL_POSTULATION_CRITERIA_KEY,
        HC_MANUAL_POSTULATION_CRITERIA_DEFAULT,
    )

    if not configured_value:
        return []

    if isinstance(configured_value, str):
        configured_value = configured_value.split(",")

    if not isinstance(configured_value, list):
        return []

    return [criterion.strip() for criterion in configured_value if criterion and criterion.strip()]


def _update_hc_available_approvals(delta: int) -> int:
    with transaction.atomic():
        setting_row = GeneralSettings.objects.select_for_update().filter(
            name_key=HC_APPROVAL_BAG_SIZE_KEY,
        ).first()

        if setting_row is None:
            current_value = HC_AVAILABLE_APPROVALS_DEFAULT
            setting_row = GeneralSettings(
                name_key=HC_APPROVAL_BAG_SIZE_KEY,
                value=str(current_value),
                category="engine_participation",
                data_type="INT",
                description="Products available to approve into SDT",
                status=True,
            )
        else:
            current_value = _normalize_int(
                setting_row.value,
                default=HC_AVAILABLE_APPROVALS_DEFAULT,
            )

        next_value = current_value + delta
        setting_row.value = str(next_value)
        if not setting_row.data_type:
            setting_row.data_type = "INT"
        if setting_row.status is None:
            setting_row.status = True
        setting_row.save()

    _clear_general_setting_cache(HC_APPROVAL_BAG_SIZE_KEY)
    return next_value


def _consume_hc_available_approval() -> int:
    with transaction.atomic():
        setting_row = GeneralSettings.objects.select_for_update().filter(
            name_key=HC_APPROVAL_BAG_SIZE_KEY,
        ).first()
        if setting_row is None:
            current_value = HC_AVAILABLE_APPROVALS_DEFAULT
            setting_row = GeneralSettings(
                name_key=HC_APPROVAL_BAG_SIZE_KEY,
                value=str(current_value),
                category="engine_participation",
                data_type="INT",
                description="Products available to approve into SDT",
                status=True,
            )
        else:
            current_value = _normalize_int(
                setting_row.value,
                default=HC_AVAILABLE_APPROVALS_DEFAULT,
            )

        if current_value <= 0:
            raise InvalidHCParticipationTransition(
                "No available approvals. Review removal requests already_in_hc to increase available approvals."
            )

        next_value = current_value - 1
        setting_row.value = str(next_value)
        if not setting_row.data_type:
            setting_row.data_type = "INT"
        if setting_row.status is None:
            setting_row.status = True
        setting_row.save()

    _clear_general_setting_cache(HC_APPROVAL_BAG_SIZE_KEY)
    return next_value


def get_hc_participation_summary() -> dict:
    postulated_products = HCParticipation.objects.filter(
        recommendation__in=("postulated", "postulated_manually"),
        status__in=ACTIVE_HC_REQUEST_STATUSES,
    ).values("product_id").distinct().count()

    preselected_products = 0
    preselected_requests = HCParticipation.objects.filter(
        recommendation__in=("postulated", "postulated_manually"),
        status="Pending",
    ).only("security_posture_data")
    for request in preselected_requests:
        if is_hc_request_preselected(request):
            preselected_products += 1

    latest_by_product = {}
    for request in HCParticipation.objects.only(
        "product_id",
        "recommendation",
        "status",
        "create_date",
    ).order_by("product_id", "-create_date"):
        if request.product_id not in latest_by_product:
            latest_by_product[request.product_id] = request

    products_in_hc = 0
    for latest in latest_by_product.values():
        if latest.recommendation in ("postulated", "postulated_manually"):
            # Reviewer approval (Reviewed) already commits the product into SDT
            if latest.status in ("Reviewed", "Approved"):
                products_in_hc += 1
        elif latest.recommendation == "already_in_hc":
            # Once reviewer approves removal (Reviewed), product leaves SDT
            if latest.status in ("Pending", "Rejected"):
                products_in_hc += 1

    return {
        "available_approvals": get_hc_available_approvals(),
        "postulated_products": postulated_products,
        "preselected_products": preselected_products,
        "products_in_hc": products_in_hc,
    }


def is_hc_request_preselected(hc_participation) -> bool:
    security_posture_data = hc_participation.security_posture_data
    if not isinstance(security_posture_data, dict):
        return False
    return bool(security_posture_data.get(HC_PRESELECTED_FLAG_KEY, False))


def set_hc_request_preselection(hc_participation, is_preselected: bool):
    with transaction.atomic():
        locked_hc_participation = HCParticipation.objects.select_for_update().get(pk=hc_participation.pk)

        if locked_hc_participation.recommendation not in ("postulated", "postulated_manually"):
            raise InvalidHCParticipationTransition(
                "Only postulated requests can be pre-selected."
            )

        if locked_hc_participation.status != "Pending":
            raise InvalidHCParticipationTransition(
                "Only pending postulated requests can be pre-selected."
            )

        security_posture_data = locked_hc_participation.security_posture_data
        if not isinstance(security_posture_data, dict):
            security_posture_data = {}

        currently_preselected = bool(security_posture_data.get(HC_PRESELECTED_FLAG_KEY, False))
        if currently_preselected == is_preselected:
            return locked_hc_participation

        if is_preselected:
            _update_hc_available_approvals(-1)
        else:
            _update_hc_available_approvals(1)

        security_posture_data[HC_PRESELECTED_FLAG_KEY] = is_preselected
        locked_hc_participation.security_posture_data = security_posture_data
        locked_hc_participation.save()

    return locked_hc_participation


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

    operative_username = (getattr(settings, "OPERATIVE_USER", "") or "").strip()
    fallback_user = None
    if operative_username:
        fallback_user = Dojo_User.objects.filter(username=operative_username).first()

    if fallback_user:
        return fallback_user

    raise ValueError(
        "Unable to resolve the operative user token to call HC participation endpoint."
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

    try:
        response = requests.post(
            endpoint_url,
            json=request_body,
            headers=_build_hc_auth_headers(token_key),
            timeout=timeout_seconds,
            verify=False,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.error("HC microservice call failed for %s: %s", endpoint_url, exc)
        return []
    except ValueError as exc:
        logger.error("HC microservice returned invalid JSON for %s: %s", endpoint_url, exc)
        return []

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
            default_reason = "Product already in SDT. Review required to continue."
        elif recommendation == "not_eligible":
            default_reason = "Product is not eligible for Specialized DevSecOps Tests."
        else:
            default_reason = "Postulated to Specialized DevSecOps Tests."

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
        subject=f"🎯 {len(requests)} new SDT requests",
        title=f"New Specialized DevSecOps Tests participation requests",
        description=(
            f"{len(requests)} new SDT participation requests have been generated "
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


def get_manual_hc_postulation_eligibility_error(product) -> str | None:
    allowed_class_ids = list(getattr(settings, "HC_PARTICIPATION_POSTULATED_CLASSID", []))
    product_class_id = _get_product_class_id_from_description(product)
    if allowed_class_ids and product_class_id not in allowed_class_ids:
        return (
            "This product class_id is not allowed for HC postulation. "
            f"Allowed class_id values: {', '.join(allowed_class_ids)}."
        )

    if is_product_in_hacking_continuous_from_requests(product):
        return "This product is already in SDT."

    pending_postulation_exists = HCParticipation.objects.filter(
        product=product,
        status="Pending",
        recommendation__in=("postulated", "postulated_manually"),
    ).exists()
    if pending_postulation_exists:
        return "A pending HC postulation already exists for this product."

    return None


def create_manual_hc_postulation(product, user, criteria=None):
    criteria = list(criteria or [])
    if not criteria:
        return None, "You must select at least one criterion to submit the manual postulation."

    with transaction.atomic():
        locked_product = Product.objects.select_for_update().get(pk=product.pk)

        eligibility_error = get_manual_hc_postulation_eligibility_error(locked_product)
        if eligibility_error:
            return None, eligibility_error

        batch_id = uuid.uuid4()
        requested_by = getattr(user, "username", "System")
        criteria_text = "; ".join(criteria)
        hc_request = HCParticipation.objects.create(
            product=locked_product,
            recommendation="postulated_manually",
            business_criticality=locked_product.business_criticality,
            was_in_hacking_continuous=False,
            security_posture_data={
                "product_risk_posture_url": _build_product_risk_posture_url(locked_product.id),
                "manual_postulation_criteria": criteria,
            },
            reason=(
                f"Manual postulation created from Product view by {requested_by}. "
                f"Criteria met: {criteria_text}."
            ),
            status="Pending",
            created_by=user,
            batch_id=batch_id,
        )

    _notify_reviewers_of_new_requests([hc_request], batch_id)
    return hc_request, None


def delete_hc_participation_records_by_date_range(start_date, end_date):
    if start_date is None or end_date is None:
        raise ValueError("Both start_date and end_date are required.")

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    queryset = HCParticipation.objects.filter(
        create_date__date__gte=start_date,
        create_date__date__lte=end_date,
    )
    matched_records = queryset.count()
    deleted_count, deleted_by_model = queryset.delete()

    logger.info(
        "Deleted %s HCParticipation record(s) created between %s and %s.",
        matched_records, start_date, end_date,
    )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "matched_records": matched_records,
        "deleted_count": deleted_count,
        "deleted_by_model": deleted_by_model,
    }


def mark_hc_participation_reviewed(hc_participation, user, confirmation_criteria=None):
    with transaction.atomic():
        locked_hc_participation = HCParticipation.objects.select_for_update().get(pk=hc_participation.pk)
        _validate_hc_status_transition(locked_hc_participation.status, "Reviewed")

        is_postulation_request = locked_hc_participation.recommendation in (
            "postulated",
            "postulated_manually",
        )
        is_already_in_hc_request = locked_hc_participation.recommendation == "already_in_hc"
        was_preselected = is_hc_request_preselected(locked_hc_participation)

        current_available_approvals = get_hc_available_approvals()
        if is_postulation_request and current_available_approvals < 0:
            raise InvalidHCParticipationTransition(
                "Available approvals is negative. Remove pre-selections or review already_in_hc removals before reviewing more postulated requests."
            )

        if is_postulation_request and not was_preselected:
            _consume_hc_available_approval()

        if is_postulation_request and was_preselected:
            security_posture_data = locked_hc_participation.security_posture_data
            if not isinstance(security_posture_data, dict):
                security_posture_data = {}
            security_posture_data[HC_PRESELECTED_FLAG_KEY] = False
            locked_hc_participation.security_posture_data = security_posture_data

        if is_postulation_request and confirmation_criteria:
            security_posture_data = locked_hc_participation.security_posture_data
            if not isinstance(security_posture_data, dict):
                security_posture_data = {}
            security_posture_data[HC_INGRESS_CONFIRMATION_CRITERIA_KEY] = list(confirmation_criteria)
            locked_hc_participation.security_posture_data = security_posture_data

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
            review_note = "Request marked as reviewed for SDT continuity decision"

        HCParticipationLog.objects.create(
            hc_participation=locked_hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Reviewed",
            notes=review_note,
        )

        if is_already_in_hc_request:
            _update_hc_available_approvals(1)

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

        approval_note = "Request approved for SDT participation"
        if hc_participation.was_in_hacking_continuous:
            approval_note = "Request approved for removal from SDT"

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
            description=f"The SDT participation request for product {hc_participation.product.name} has been approved.",
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
        is_postulation_request = hc_participation.recommendation in ("postulated", "postulated_manually")
        is_already_in_hc_request = hc_participation.recommendation == "already_in_hc"

        security_posture_data = hc_participation.security_posture_data
        if not isinstance(security_posture_data, dict):
            security_posture_data = {}

        was_preselected = bool(security_posture_data.pop(HC_PRESELECTED_FLAG_KEY, False))
        should_restore_approval = was_preselected or (
            is_postulation_request and previous_status == "Reviewed"
        )
        if should_restore_approval:
            _update_hc_available_approvals(1)

        # If an already_in_hc removal request was reviewed first, review already gave +1.
        # Rejecting that removal means the product stays in HC, so we revert with -1.
        if is_already_in_hc_request and previous_status == "Reviewed":
            _update_hc_available_approvals(-1)

        hc_participation.security_posture_data = security_posture_data

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
            rejection_note = "Request rejected: product remains in SDT"

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
            description=f"The SDT participation request for product {hc_participation.product.name} has been rejected.",
            url=reverse("hc_participation", args=[str(hc_participation.pk)]),
            recipients=[hc_participation.created_by.username],
            icon="times-circle",
            color_icon="#dc3545",
        )

    return hc_participation


def return_hc_participation_to_pending(hc_participation, user, reason: str = ""):
    with transaction.atomic():
        hc_participation = HCParticipation.objects.select_for_update().get(pk=hc_participation.pk)

        previous_status = hc_participation.status
        if previous_status == "Pending":
            return hc_participation

        allowed_statuses = {"Reviewed", "Approved", "Rejected"}
        if previous_status not in allowed_statuses:
            raise InvalidHCParticipationTransition(
                f"Cannot return HC request from {previous_status} to Pending. "
                f"Allowed previous statuses: {', '.join(sorted(allowed_statuses))}."
            )

        is_postulation_request = hc_participation.recommendation in ("postulated", "postulated_manually")
        is_already_in_hc_request = hc_participation.recommendation == "already_in_hc"

        if is_postulation_request and previous_status in {"Reviewed", "Approved"}:
            _update_hc_available_approvals(1)

        if is_already_in_hc_request and previous_status in {"Reviewed", "Approved"}:
            _update_hc_available_approvals(-1)

        current_time = timezone.now()
        hc_participation.status = "Pending"
        hc_participation.final_status = None
        hc_participation.status_updated_at = current_time
        hc_participation.status_updated_by = user
        hc_participation.save()

        log_note = "Request returned to Pending for reevaluation"
        if reason:
            log_note = f"{log_note}. Reason: {reason.strip()}"

        HCParticipationLog.objects.create(
            hc_participation=hc_participation,
            changed_by=user,
            previous_status=previous_status,
            current_status="Pending",
            notes=log_note,
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




