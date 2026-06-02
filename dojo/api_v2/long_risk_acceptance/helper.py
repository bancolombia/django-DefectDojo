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

def to_execute_rule(query: QuerySet[Finding], rules: list[dict]) -> QuerySet[Finding]:
    combined_rules_include = {}
    combined_rules_exclude = {}
    for rule in rules:
        if not rule:
            return query
        if rule.filters:
            combined_rules_include.update(rule.filters)
        if rule.exclusions:
            combined_rules_exclude.update(rule.exclusions)

    return query.exclude(**combined_rules_exclude).filter(**combined_rules_include)

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

@app.task
def async_apply_rule_long_risk_acceptance(ra_engagement_id, user_id):
    ra_engagement = get_object_or_404(RiskAcceptanceEngagement, id=ra_engagement_id) 
    user = get_object_or_404(User, id=user_id)
    finding_qs = render_rule(ra_engagement)
    if finding_qs:
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
