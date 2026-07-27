import logging

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


@dojo_async_task
@app.task
def update_sla_expiration_dates_sla_config_async(sla_config, products, severities, *args, **kwargs):
    update_sla_expiration_dates_sla_config_sync(sla_config, products, severities)


@dojo_async_task
@app.task
def update_sla_expiration_dates_product_async(product, sla_config, *args, **kwargs):
    update_sla_expiration_dates_sla_config_sync(sla_config, [product])


def update_sla_expiration_dates_sla_config_sync(sla_config, products, severities=None):
    logger.info(f"Updating finding SLA expiration dates within the {sla_config} SLA configuration")
    # update each finding that is within the SLA configuration that was saved
    findings = Finding.objects.filter(test__engagement__product__sla_configuration_id=sla_config.id, active=True)
    if products:
        findings = findings.filter(test__engagement__product__in=products)
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

    findings = findings.prefetch_related(
            "test",
            "test__engagement",
            "test__engagement__product",
            "test__engagement__product__sla_configuration",
    )

    findings = findings.order_by("id").only("id", "sla_start_date", "date", "severity", "test")

    mass_model_updater(Finding, findings, lambda f: f.set_sla_expiration_date(), fields=["sla_expiration_date"])

    # reset the async updating flag to false for all products using this sla config
    for product in products:
        product.async_updating = False
        super(Product, product).save()
        calculate_grade(product)

    # reset the async updating flag to false for this sla config
    sla_config.async_updating = False
    super(SLA_Configuration, sla_config).save()
    logger.info(f"DONE Updating finding SLA expiration dates within the {sla_config} SLA configuration")
