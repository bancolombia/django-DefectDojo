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

    def _get_recipients(long_risk_acceptance):
        recipients = []
        if long_risk_acceptance.reviewed_by:
            recipients.append(long_risk_acceptance.reviewed_by)
        
        if long_risk_acceptance.accepted_by:
            recipients.append(long_risk_acceptance.accepted_by)

        if long_risk_acceptance.owner:
            username = long_risk_acceptance.owner.get_username()
            if username:
                recipients.append(username)
        return recipients

    @staticmethod
    def risk_acceptance_request(*args, **kwargs):
        long_risk_acceptance = kwargs["long_risk_acceptance"]
        title = f"📋 {long_risk_acceptance.description[:50]}"
        recipients = Notification._get_recipients(long_risk_acceptance)
        long_term = long_risk_acceptance.expiration_date.date() - timezone.now().date()
        description = f"<b>📋 NEW REQUEST:</b> Long-term risk acceptance for {long_term.days} days is <b>pending approval</b>",
        subject = f"📋 NEW: Long-term Risk Acceptance Request #{long_risk_acceptance.id}"
        if recipients:
            create_notification(event='long_risk_acceptance_request',
                            title=title, long_risk_acceptance=long_risk_acceptance,
                            subject=subject,
                            description=description,
                            recipients=recipients,
                            icon="bell",
                            owner=long_risk_acceptance.owner,
                            color_icon="#0056b3",
                            url=reverse('view_long_risk_acceptance_details', args=(long_risk_acceptance.id,)))

    @staticmethod
    def risk_acceptance_approved(*args, **kwargs):
        long_risk_acceptance = kwargs["long_risk_acceptance"]
        title = f"✓ {long_risk_acceptance.description[:50]}"
        long_term = long_risk_acceptance.expiration_date.date() - timezone.now().date()
        description = f"<b>✓ APPROVED:</b> Long-term risk acceptance for {long_term.days} days has been <b>APPROVED</b> by {long_risk_acceptance.reviewed_by}",
        subject = f"✅ APPROVED: Long-term Risk Acceptance #{long_risk_acceptance.id}"
        recipients = Notification._get_recipients(long_risk_acceptance)
        if recipients:
            create_notification(event='long_risk_acceptance_approved',
                            title=title, long_risk_acceptance=long_risk_acceptance,
                            subject=subject,
                            description=description,
                            recipients=recipients,
                            icon="bell",
                            owner=long_risk_acceptance.owner,
                            color_icon="#28a745",
                            url=reverse('view_long_risk_acceptance_details', args=(long_risk_acceptance.id,)))
 
    @staticmethod
    def risk_acceptance_expiration(long_risk_acceptance,
                                   title=None):
        from dojo.api_v2.long_risk_acceptance.helper import render_rule
        title = f"{long_risk_acceptance.description[:50]}"
        long_term = long_risk_acceptance.expiration_date.date() - timezone.now().date()
        description = f"Expiration <b>long-term</b> of {long_term.days} days for the findings",
        subject = f"🙋‍♂️Expiration of aceptance long term of risk {long_risk_acceptance.id}  🙏"
        recipients = Notification._get_recipients(long_risk_acceptance)
        if recipients:
            create_notification(
                event='long_risk_acceptance_expiration',
                subject=subject,
                title=title,
                product=long_risk_acceptance.product,
                long_risk_acceptance=long_risk_acceptance,
                findings_count=qr.count() if (qr := render_rule(long_risk_acceptance, True)) else 0,
                recipients=recipients,
                description=description,
                icon="bell",
                color_icon="#A7A40B",
                url=reverse('view_long_risk_acceptance_details',  args=(long_risk_acceptance.id,))
            )

