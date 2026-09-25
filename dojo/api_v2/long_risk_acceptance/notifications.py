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
    def risk_acceptance_approved(*args, **kwargs):
        long_risk_acceptance = kwargs["long_risk_acceptance"]
        title = f"{long_risk_acceptance.description[:50]}"
        recipients = [long_risk_acceptance.reviewed_by]
        long_term = long_risk_acceptance.expiration_date.date() - timezone.now().date()
        description = f"requested acceptance <b>long-term</b> of {long_term.days} days for the findings",
        subject = f"🙋‍♂️Request of aceptance long term of risk {long_risk_acceptance.id}  🙏"

        create_notification(event='long_risk_acceptance_approved',
                        title=title, risk_acceptance=long_risk_acceptance,
                        subject=subject,
                        description=description,
                        recipients=recipients,
                        icon="bell",
                        owner=long_risk_acceptance.owner,
                        color_icon="#104dbe",
                        url=reverse('view_long_risk_acceptance_details', args=(long_risk_acceptance.id,)))
 
    @staticmethod
    def risk_acceptance_expiration(long_risk_acceptance,
                                   title=None):

        title = f"{long_risk_acceptance.description[:50]}"
        long_term = long_risk_acceptance.expiration_date.date() - timezone.now().date()
        description = f"Expiration <b>long-term</b> of {long_term.days} days for the findings",
        subject = f"🙋‍♂️Expiration of aceptance long term of risk {long_risk_acceptance.id}  🙏"
        recipients = []
        if long_risk_acceptance.accepted_by:
            recipients.append(long_risk_acceptance.accepted_by)

        if long_risk_acceptance.owner:
            username = long_risk_acceptance.owner.get_username()
            if username:
                recipients.append(username)

        if recipients:
            create_notification(
                event='long_risk_acceptance_expiration',
                subject=subject,
                title=title,
                product=long_risk_acceptance.product,
                recipients=recipients,
                description=description,
                icon="bell",
                color_icon="#A7A40B",
                url=reverse('view_long_risk_acceptance_details',  args=(long_risk_acceptance.id,))
            )

