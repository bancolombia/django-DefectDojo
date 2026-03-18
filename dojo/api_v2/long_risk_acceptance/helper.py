from dojo.api_v2.api_error import ApiError
from dojo.api_v2.long_risk_acceptance.models import RiskAcceptanceEngagement 
from dojo.models import Finding
from django.utils import timezone
from django.db.models.query import QuerySet
from django.db import transaction
from django.db.models import Q

def to_execute_rule(query: QuerySet[Finding], rules: list[dict]) -> QuerySet[Finding]:
    combined_rules_include = {}
    combined_rules_exclude = {}
    for rule in rules:
        if not rule:
            #TODO: Add rule black_list 
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



def apply_rule(ra_engagement: RiskAcceptanceEngagement):
    finding_qs = render_rule(ra_engagement)

    for finding in finding_qs.iterator(chunk_size=200):
        if finding.risk_status == "Risk Active":
          
            finding.risk_status = "Risk Accepted"
            finding.active = False
            finding.risk_accepted = True

            finding.save(update_fields=[
                "risk_status",
                "active",
                "risk_accepted"
            ])

            finding.tags.add("long_term_risk_acceptance")
