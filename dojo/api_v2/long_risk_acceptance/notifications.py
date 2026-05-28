import logging
from typing import List
from django.urls import reverse
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from dojo.notifications.helper import create_notification
from dojo.models import Finding, Risk_Acceptance
from dojo.api_v2.long_risk_acceptance.serializers import RiskAcceptanceEngagementSerializer 
logger = logging.getLogger(__name__)

class Notification:

    @staticmethod
    def risk_acceptance_request(*args, **kwargs):
        long_risk_acceptance = kwargs["long_risk_acceptance"]
        product = long_risk_acceptance.product
        product_type = product.prod_type
        title = f"{long_risk_acceptance.description[:50]}"
        recipients = [long_risk_acceptance.reviewed_by]
        long_term = long_risk_acceptance.expiration_date.date() - timezone.now().date()
        description = f"requested acceptance <b>long-term</b> of {long_term.days} days for the findings that are part of <b>{product_type}</b> of aplication <b>{product}</b>",
        subject = f"🙋‍♂️Request of aceptance long term of risk {long_risk_acceptance.id}  🙏"

        create_notification(event='risk_acceptance_request',
                        title=title, risk_acceptance=long_risk_acceptance,
                        subject=subject,
                        product=long_risk_acceptance.product,
                        description=description,
                        recipients=recipients,
                        icon="bell",
                        owner=long_risk_acceptance.owner,
                        color_icon="#104dbe",
                        url=reverse('view_long_risk_acceptance_details', args=(long_risk_acceptance.id,)))
 
    @staticmethod
    def risk_acceptance_expiration(long_risk_acceptance,
                                   reactivated_findings=None,
                                   title=None):
        accepted_findings = long_risk_acceptance.accepted_findings.filter(
            is_mitigated=False,
            risk_status="Risk Accepted")
        if accepted_findings.count() == 0:
            logger.debug("RISK_ACCETANCE_EXPIRATION: Not found findings in Risk Acceptance")
            return True
        if title is None:
            title = 'Risk acceptance with ' + str(len(accepted_findings)) + " accepted findings has expired for " + \
                    str(long_risk_acceptance.engagement.product) + ': ' + str(long_risk_acceptance.engagement.name)

        create_notification(
            event='risk_acceptance_expiration',
            subject=f"⚠️Acceptance request Risk_Acceptance: {long_risk_acceptance.id} has expired🔔",
            title=title, risk_acceptance=long_risk_acceptance, accepted_findings=accepted_findings,
            reactivated_findings=reactivated_findings,
            product=long_risk_acceptance.product,
            recipients=long_risk_acceptance.accepted_by_user + [long_risk_acceptance.owner.get_username()],
            url=reverse('view_risk_acceptance', args=(long_risk_acceptance.engagement.id, long_risk_acceptance.id, ))) # TODO: IMPLEMENTAR REVERSE
