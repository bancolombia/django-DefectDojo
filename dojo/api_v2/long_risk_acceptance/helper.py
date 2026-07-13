import logging
from dojo.api_v2.api_error import ApiError
from dojo.celery import app
from dojo.api_v2.long_risk_acceptance.models import RiskAcceptanceEngagement 
from dojo.models import Finding
from django.utils import timezone
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
from django.db import transaction
from dojo.models import User
from django.db.models import Q
logger = logging.getLogger(__name__)

def parse_filter_values(filter_string: str) -> list[str]:
    if not filter_string:
        return []
    return [value.strip() for value in filter_string.split(',') if value.strip()]

def apply_dynamic_filter(query: QuerySet[Finding], filter_field: str, filter_values: str) -> QuerySet[Finding]:
    """
    Aplica un filtro dinámico a nivel de BD.
    
    Ejemplo:
        apply_dynamic_filter(Finding.objects.all(), "cve", "CVE-2024-1,CVE-2024-2")
        -> Retorna findings con ese CVE
    
    Args:
        query: QuerySet de Finding
        filter_field: Campo a filtrar (ej: "cve", "severity", "title")
        filter_values: String de valores separados por comas
    
    Returns:
        QuerySet filtrado
    """
    values = parse_filter_values(filter_values)
    if not values:
        return query
    
    # Crear un Q object con OR para múltiples valores
    q_filter = Q()
    for value in values:
        q_filter |= Q(**{f"{filter_field}__icontains": value})
    
    return query.filter(q_filter)

def to_execute_rule(query: QuerySet[Finding], rules: list[dict]) -> QuerySet[Finding]:
    """
    Ejecuta las reglas de filtro sobre un QuerySet de findings.
    Maneja filtros que pueden ser strings con valores separados por comas.
    
    Estructura esperada de rules:
    {
        "filters": {"cve": "CVE-2024-1,CVE-2024-2", "severity": "High"},
        "exclusions": {"title__icontains": "test"}
    }
    """
    combined_rules_include = Q()
    combined_rules_exclude = Q()
    
    for rule in rules:
        if not rule:
            return query
        
        if rule.filters:
            for field, value in rule.filters.items():
                if isinstance(value, str) and ',' in value:
                    values = parse_filter_values(value)
                    q_filter = Q()
                    for v in values:
                        q_filter |= Q(**{f"{field}__icontains": v})
                    combined_rules_include &= q_filter
                else:
                    combined_rules_include &= Q(**{field: value})
        
        if rule.exclusions:
            for field, value in rule.exclusions.items():
                if isinstance(value, str) and ',' in value:
                    values = parse_filter_values(value)
                    q_filter = Q()
                    for v in values:
                        q_filter |= Q(**{f"{field}__icontains": v})
                    combined_rules_exclude |= q_filter
                else:
                    combined_rules_exclude |= Q(**{field: value})

    if combined_rules_include:
        query = query.filter(combined_rules_include)
    if combined_rules_exclude:
        query = query.exclude(combined_rules_exclude)
    
    return query

def render_rule(ra_engagement: RiskAcceptanceEngagement):
    rules = ra_engagement.riskacceptanceexclusionrule_set.all()
    finding_qr = None
    for eng in ra_engagement.engagement_set.all():
        query = eng.get_all_finding_active
        if finding_qr is None:
            finding_qr = to_execute_rule(query, rules)
        else:
            finding_qr = finding_qr.union(to_execute_rule(query, rules))

    return finding_qr


def apply_review(request, ra_engagement: RiskAcceptanceEngagement):
    ra_engagement.risk_status = "Risks Reviewed"
    ra_engagement.reviewed_by = request.user.username
    ra_engagement.reviewed_date = timezone.now()
    ra_engagement.save()

def active_findings_long_risk_acceptance(finding_qs: QuerySet[Finding]):
    for finding in finding_qs.iterator(chunk_size=200):
        finding.risk_status = "Risk Active"
        finding.active = True
        finding.risk_accepted = False

        finding.save(update_fields=[
            "risk_status",
            "active",
            "risk_accepted"
        ])
        finding.tags.remove("long_term_risk_acceptance")

@app.task
def async_apply_rule_long_risk_acceptance(ra_engagement_id, user_id, event):
    ra_engagement = get_object_or_404(RiskAcceptanceEngagement, id=ra_engagement_id) 
    user = get_object_or_404(User, id=user_id)
    finding_qs = render_rule(ra_engagement)
    if finding_qs:
        if event == "reject":
            if ra_engagement.risk_status in ["Risks Reviewed"]:
                ra_engagement.risk_status = "Risks Rejected"
                ra_engagement.save()
            elif ra_engagement.risk_status in ["Risks Accepted"]:
                ra_engagement.risk_status = "Risks Rejected"
                ra_engagement.save()
                active_findings_long_risk_acceptance(finding_qs)
        if ra_engagement.risk_status in ["Risks Reviewed"]:
            ra_engagement.risk_status = "Risks Accepted"
            ra_engagement.save()
            for finding in finding_qs.iterator(chunk_size=200):
                finding.risk_status = "Risk Accepted"
                finding.active = False
                finding.risk_accepted = True

                finding.save(update_fields=[
                    "risk_status",
                    "active",
                    "risk_accepted"
                ])
                logger.debug(f"finding {finding.id} accepted flow long term risk acceptance of engagement {ra_engagement.id}")
                finding.tags.add("long_term_risk_acceptance")

        elif ra_engagement.risk_status in ["Risks Pending"]:
            ra_engagement.risk_status = "Risks Reviewed"
            ra_engagement.reviewed_by = user.username
            ra_engagement.reviewed_date = timezone.now()
            ra_engagement.save()
    else:
        raise ApiError("No findings found for this engagement with the current rules.")
