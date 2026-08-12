import logging
import datetime

from django.core.cache import cache

from dojo.celery import app
from dojo.decorators import dojo_async_task
from dojo.models import Finding, GeneralSettings, Product, SLA_Configuration
from dojo.utils import calculate_grade, mass_model_updater

logger = logging.getLogger(__name__)

# Maps a changed SLA_Configuration severity field (lower-cased) to the equivalent
# priority_classification label, mirroring Finding.get_severity_related_to_priority()
SEVERITY_TO_PRIORITY_CLASSIFICATION = {
    "critical": "Very Critical",
    "high": "Critical",
    "medium": "High",
    "low": "Medium Low",
}
# Same mapping used by FindingPriorityFilter's choices (e.g. dojo/engagement/views.py)
PRIORITY_CLASSIFICATION_TO_FILTER_VALUE = {
    "Very Critical": 4,
    "Critical": 3,
    "High": 2,
    "Medium Low": 1,
    "Unknown": 0,
}

# Optional global setting: if this variable contains tags, only findings with
# those tags are included in SLA expiration date recalculation.
SLA_FINDINGS_TAGS_FILTER_SETTING = "SLA_FINDINGS_TAGS_FILTER"

# Optional global setting: when enabled, sla_expiration_date is recalculated only
# for findings whose sla_start_date matches the azure_devops_next_sprint_start_date cache value.
SLA_FINDINGS_START_DATE_FILTER_SETTING = "SLA_FINDINGS_START_DATE_FILTER"


def _normalize_tags_filter_value(tags_value):
    if not tags_value:
        return []

    if isinstance(tags_value, str):
        raw_tags = tags_value.split(",")
    elif isinstance(tags_value, (list, tuple, set)):
        raw_tags = list(tags_value)
    else:
        return []

    return [str(tag).strip().lower() for tag in raw_tags if str(tag).strip()]


@dojo_async_task
@app.task
def update_sla_expiration_dates_sla_config_async(sla_config, product_ids, severities, *args, **kwargs):
    update_sla_expiration_dates_sla_config_sync(sla_config, product_ids=product_ids, severities=severities)


@dojo_async_task
@app.task
def update_sla_expiration_dates_product_async(product, sla_config, *args, **kwargs):
    update_sla_expiration_dates_sla_config_sync(sla_config, product_ids=[product.id])


def update_sla_expiration_dates_sla_config_sync(sla_config, product_ids=None, severities=None):
    logger.info(f"Updating finding SLA expiration dates within the {sla_config} SLA configuration")
    target_products = Product.objects.filter(sla_configuration_id=sla_config.id)
    if product_ids:
        target_products = target_products.filter(id__in=product_ids)

    # update each finding that is within the SLA configuration that was saved
    findings = Finding.objects.filter(test__engagement__product__sla_configuration_id=sla_config.id, active=True)
    if product_ids:
        findings = findings.filter(test__engagement__product_id__in=product_ids)
    if severities:
        if (
            GeneralSettings.get_value(name_key="PRIORITIZATION_MODEL_SEVERITY", default=True) is False and
            GeneralSettings.get_value(name_key="PRIORITIZATION_MODEL_PRIORITY", default=True) is True
        ):
            # PRIORITY model active: translate the changed severities into their equivalent
            # priority_classification values and filter using FindingPriorityFilter, the same
            # way it's done in dojo/engagement/views.py
            from dojo.filters import FindingPriorityFilter  # noqa: PLC0415 — local import to avoid circular dependency

            priority_values = [
                str(PRIORITY_CLASSIFICATION_TO_FILTER_VALUE[SEVERITY_TO_PRIORITY_CLASSIFICATION[severity.lower()]])
                for severity in severities
                if severity.lower() in SEVERITY_TO_PRIORITY_CLASSIFICATION
            ]
            findings = FindingPriorityFilter().filter(findings, priority_values)
        else:
            findings = findings.filter(severity__in=severities)

    configured_tags_filter = []
    if GeneralSettings.objects.filter(name_key=SLA_FINDINGS_TAGS_FILTER_SETTING).exists():
        configured_tags_filter = _normalize_tags_filter_value(
            GeneralSettings.get_value(name_key=SLA_FINDINGS_TAGS_FILTER_SETTING, default=[]),
        )
    if configured_tags_filter:
        findings = findings.filter(tags__name__in=configured_tags_filter).distinct()
        logger.info(
            "Applying tag filter from GeneralSettings %s=%s",
            SLA_FINDINGS_TAGS_FILTER_SETTING,
            configured_tags_filter,
        )

    if GeneralSettings.objects.filter(name_key=SLA_FINDINGS_START_DATE_FILTER_SETTING).exists():
        start_date_filter_enabled = GeneralSettings.get_value(name_key=SLA_FINDINGS_START_DATE_FILTER_SETTING, default=False)
        if start_date_filter_enabled:
            filter_date = cache.get("azure_devops_next_sprint_start_date")
            if isinstance(filter_date, datetime.datetime):
                filter_date = filter_date.date()
            elif isinstance(filter_date, str):
                try:
                    filter_date = datetime.date.fromisoformat(filter_date[:10])
                except ValueError:
                    logger.warning(
                        "Invalid cached azure_devops_next_sprint_start_date value: %s",
                        filter_date,
                    )
                    filter_date = None
            if filter_date:
                findings = findings.filter(sla_start_date=filter_date)
                logger.info(
                    "Applying start date filter from cache azure_devops_next_sprint_start_date: sla_start_date=%s",
                    filter_date,
                )

    

    findings = findings.prefetch_related(
            "test",
            "test__engagement",
            "test__engagement__product",
            "test__engagement__product__sla_configuration",
    )

    findings = findings.order_by("id").only("id", "sla_start_date", "date", "severity", "test")

    mass_model_updater(Finding, findings, lambda f: f.set_sla_expiration_date(), fields=["sla_expiration_date"])

    # reset async flag in bulk for all affected products
    impacted_products = list(target_products.only("id", "name"))
    if impacted_products:
        impacted_product_ids = [product.id for product in impacted_products]
        Product.objects.filter(id__in=impacted_product_ids).update(async_updating=False)

        for product in impacted_products:
            calculate_grade(product)

    # reset the async updating flag to false for this sla config
    sla_config.async_updating = False
    super(SLA_Configuration, sla_config).save()
    logger.info(f"DONE Updating finding SLA expiration dates within the {sla_config} SLA configuration")
