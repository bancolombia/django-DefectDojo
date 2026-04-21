import logging
from collections import defaultdict

from django.db.models import Count, Q, Sum
from django.utils import timezone

from dojo.api_v2.utils import http_response
from dojo.models import Engagement, Finding, GeneralSettings, Product, Product_Type, Test


logger = logging.getLogger(__name__)




def _get_hc_participation_evaluation(product_id: int) -> dict:
    """
    Gets the latest HC participation evaluation for a product.
    Returns None if no evaluation exists or if module is not available.
    """
    try:
        from dojo.engine_participation.helpers import get_latest_hc_evaluation_for_product
        return get_latest_hc_evaluation_for_product(product_id)
    except ImportError:
        return None
    except Exception as e:
        logger.warning(f"Error getting HC participation evaluation for product {product_id}: {e}")
        return None

def calculate_posture(result):
    posture_status_dict = GeneralSettings.get_value("SECURITY_POSTURE_STATUS", {})
    for key, value in posture_status_dict.items():
        if result <= value:
            return key
    return list(posture_status_dict.keys())[-1] if posture_status_dict else "UNKNOWN"


def _init_priority_counter():
    return {
        "very_critical": 0,
        "critical": 0,
        "high": 0,
        "medium_low": 0,
        "unknown": 0,
    }


def _init_severity_counter():
    return {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
        "unknown": 0,
    }


def _increment_bucket(counter, key):
    bucket = str(key).lower().replace(" ", "_")
    if bucket not in counter:
        bucket = "unknown"
    counter[bucket] += 1


def _apply_total_counters(data, findings_qs):
    totals = findings_qs.aggregate(
        counter_active_findings=Count(
            "id",
            filter=Q(active=True, duplicate=False, risk_accepted=False),
        ),
        counter_total_findings=Count("id"),
        counter_accepted_findings=Count(
            "id",
            filter=Q(active=False, risk_accepted=True),
        ),
        counter_closed_findings=Count("id", filter=Q(is_mitigated=True)),
        counter_transferred_findings=Count(
            "id",
            filter=Q(active=False, risk_status="Transfer Accepted"),
        ),
        counter_onwhitelist_findings=Count(
            "id",
            filter=Q(active=False, risk_status="On Whitelist"),
        ),
    )
    for key, value in totals.items():
        data[key] = value or 0


def _collect_events(data, active_findings_qs):
    event_tags = GeneralSettings.get_value("HACKING_CONTINUOUS_EVENT_TAGS", [])
    if not event_tags:
        return

    events = (
        active_findings_qs.filter(is_mitigated=False, tags__name__in=event_tags)
        .distinct()
        .only("id", "title", "description")
    )

    for event in events:
        data["events_active_hacking"]["status"] = True
        data["events_active_hacking"]["events"].append(
            {
                "id": event.id,
                "name": event.title,
                "description": event.description,
            }
        )


def _classify_active_findings(data, active_findings_qs):
    result = 0
    for finding in active_findings_qs.prefetch_related("tags"):
        priority = finding.priority_classification
        logger.debug("Finding %s has priority %s", finding.id, priority)
        _increment_bucket(data["counter_findings_by_priority"], priority)
        _increment_bucket(data["counter_findings_by_severity"], finding.severity)
        result += finding.priority
    return round(result, 3)


def adoption_devsecops_include(tags):
    tags = list(set(tags))
    return [
        tag
        for tag in tags
        if tag in GeneralSettings.get_value("DEVSECOPS_ADOPTION_INCLUDE_TAGS", ["engine_iac", "engine_container"])
    ]


def is_in_hacking_continuous(test, data, test_tags=None, hacking_tags=None, days_tolerance=None):
    tag_names = test_tags if test_tags is not None else list(test.tags.all().values_list("name", flat=True))
    valid_hacking_tags = set(hacking_tags if hacking_tags is not None else GeneralSettings.get_value("HACKING_CONTINUOUS_TAGS", []))

    if set(tag_names) & valid_hacking_tags:
        present_day = timezone.now()
        valid_days_tolerance = (
            days_tolerance
            if days_tolerance is not None
            else GeneralSettings.get_value("HACKING_CONTINUOUS_DAYS_TOLERANCE", 30)
        )
        days_difference = (present_day - test.updated).days
        latest_report_hacking = days_difference <= valid_days_tolerance
        if latest_report_hacking:
            return True

        detail = (
            "SECURITY POSTURE: Test %s has Hacking Continuous tag but last update is older than %s days",
            test.id,
            valid_days_tolerance,
        )
        logger.info(detail)
        data["details"].append(detail)

    return False


def _collect_tests_context(data, tests_qs):
    tags = []
    hacking_tags = set(GeneralSettings.get_value("HACKING_CONTINUOUS_TAGS", []))
    days_tolerance = GeneralSettings.get_value("HACKING_CONTINUOUS_DAYS_TOLERANCE", 30)

    for test in tests_qs.prefetch_related("tags"):
        test_tags = [tag.name for tag in test.tags.all()]
        tags.extend(test_tags)
        if is_in_hacking_continuous(
            test,
            data,
            test_tags=test_tags,
            hacking_tags=hacking_tags,
            days_tolerance=days_tolerance,
        ) and not data["is_in_hacking_continuos"]:
            data["is_in_hacking_continuos"] = True

    data["adoption_devsecops"] = adoption_devsecops_include(tags)


def _resolve_engagement(engagement, engagement_name):
    if isinstance(engagement, Engagement):
        return engagement
    if isinstance(engagement_name, Engagement):
        return engagement_name
    return None


def _resolve_product(product, product_name):
    if isinstance(product, Product):
        return product
    if isinstance(product_name, Product):
        return product_name
    return None


def _resolve_product_type(product_type, product_type_name):
    if isinstance(product_type, Product_Type):
        return product_type
    if isinstance(product_type_name, Product_Type):
        return product_type_name
    return None


def get_engagement_security_posture(engagement: Engagement, engagement_name: str):
    data = {}
    engagement = _resolve_engagement(engagement, engagement_name)
    if not engagement:
        return http_response.not_found(message="Engagement not found", data={})

    data["engagement_name"] = engagement.name
    data["engagement_id"] = engagement.id
    data["severity_product"] = engagement.product.business_criticality
    data["is_in_hacking_continuos"] = False
    data["details"] = []
    data["events_active_hacking"] = {"status": False, "events": []}
    data["counter_findings_by_priority"] = _init_priority_counter()
    data["counter_findings_by_severity"] = _init_severity_counter()

    _collect_tests_context(data, Test.objects.filter(engagement=engagement))

    findings_qs = Finding.objects.filter(test__engagement=engagement)
    _apply_total_counters(data, findings_qs)

    active_findings_qs = findings_qs.filter(active=True, duplicate=False, risk_accepted=False)
    data["result"] = _classify_active_findings(data, active_findings_qs)
    _collect_events(data, active_findings_qs)

    data["status"] = calculate_posture(data["result"])
    return data


def get_product_security_posture(product: Product, product_name: str):
    data = {}
    product = _resolve_product(product, product_name)
    if not product:
        return http_response.not_found(message="Product not found", data={})

    data["product_id"] = product.id
    data["product_name"] = product.name
    data["severity_product"] = product.business_criticality
    data["is_in_hacking_continuos"] = False
    data["details"] = []
    data["events_active_hacking"] = {"status": False, "events": []}
    data["counter_findings_by_priority"] = _init_priority_counter()
    data["counter_findings_by_severity"] = _init_severity_counter()

    engagement_ids = list(
        Engagement.objects.filter(product=product, active=True).values_list("id", flat=True)
    )

    if not engagement_ids:
        data["adoption_devsecops"] = []
        data["counter_active_findings"] = 0
        data["counter_total_findings"] = 0
        data["counter_accepted_findings"] = 0
        data["counter_closed_findings"] = 0
        data["counter_transferred_findings"] = 0
        data["counter_onwhitelist_findings"] = 0
        data["result"] = 0.0
        data["status"] = calculate_posture(data["result"])
        return data

    _collect_tests_context(data, Test.objects.filter(engagement_id__in=engagement_ids))

    findings_qs = Finding.objects.filter(test__engagement_id__in=engagement_ids)
    _apply_total_counters(data, findings_qs)

    active_findings_qs = findings_qs.filter(active=True, duplicate=False, risk_accepted=False)
    _classify_active_findings(data, active_findings_qs)
    _collect_events(data, active_findings_qs)

    engagement_results = list(
        active_findings_qs.values("test__engagement_id").annotate(total_priority=Sum("priority"))
    )
    active_engagements_with_findings = len(engagement_results)
    result = sum(row["total_priority"] or 0 for row in engagement_results)

    data["result"] = (
        round(result / active_engagements_with_findings, 3)
        if active_engagements_with_findings > 0
        else 0.0
    )
    data["status"] = calculate_posture(data["result"])
    
    data["hc_participation_evaluation"] = _get_hc_participation_evaluation(product.id)
    
    return data


def get_product_type_security_posture(product_type: Product_Type, product_type_name: str):
    data = {}
    product_type = _resolve_product_type(product_type, product_type_name)
    if not product_type:
        return http_response.not_found(message="Product Type not found", data={})

    data["product_type_id"] = product_type.id
    data["product_type_name"] = product_type.name
    data["is_in_hacking_continuos"] = False
    data["details"] = []
    data["events_active_hacking"] = {"status": False, "events": []}
    data["counter_findings_by_priority"] = _init_priority_counter()
    data["counter_findings_by_severity"] = _init_severity_counter()

    engagement_ids = list(
        Engagement.objects.filter(product__prod_type=product_type, active=True).values_list("id", flat=True)
    )

    if not engagement_ids:
        data["adoption_devsecops"] = []
        data["counter_active_findings"] = 0
        data["counter_total_findings"] = 0
        data["counter_accepted_findings"] = 0
        data["counter_closed_findings"] = 0
        data["counter_transferred_findings"] = 0
        data["counter_onwhitelist_findings"] = 0
        data["result"] = 0.0
        data["status"] = calculate_posture(data["result"])
        return data

    _collect_tests_context(data, Test.objects.filter(engagement_id__in=engagement_ids))

    findings_qs = Finding.objects.filter(test__engagement_id__in=engagement_ids)
    _apply_total_counters(data, findings_qs)

    active_findings_qs = findings_qs.filter(active=True, duplicate=False, risk_accepted=False)
    _classify_active_findings(data, active_findings_qs)
    _collect_events(data, active_findings_qs)

    engagement_rows = active_findings_qs.values(
        "test__engagement__product_id",
        "test__engagement_id",
    ).annotate(total_priority=Sum("priority"))

    product_results = defaultdict(list)
    for row in engagement_rows:
        product_results[row["test__engagement__product_id"]].append(row["total_priority"] or 0)

    per_product_result = [
        sum(product_priorities) / len(product_priorities)
        for product_priorities in product_results.values()
        if product_priorities
    ]

    active_products_with_findings = len(per_product_result)
    data["result"] = (
        round(sum(per_product_result) / active_products_with_findings, 3)
        if active_products_with_findings > 0
        else 0.0
    )
    data["status"] = calculate_posture(data["result"])
    return data
