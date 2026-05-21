import logging
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from rest_framework.generics import GenericAPIView
from dojo.api_v2.utils import http_response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from dojo.user.queries import get_user
from dojo.home.helper import encode_string
from dojo.api_v2.notifications.serializers import SerializerEmailNotificationRiskAcceptance
from dojo.models import Risk_Acceptance, Product, Engagement, Finding
from dojo.api_v2.long_risk_acceptance.models import RiskAcceptanceEngagement
from drf_spectacular.utils import (
    extend_schema,
)
from dojo.api_v2 import (
    permissions,
)
from dojo.notifications.helper import create_notification
logger = logging.getLogger(__name__)

class NotificationEmailApiView(GenericAPIView):
    """
    Endpoint for sending risk acceptance emails asynchronously
    
    Accepts parameters:
        - async: true/false (default: true) - whether to send asynchronously
        - recipient: recipient's email address
        - subject: email subject line
        - template: email template to use
        - message: message body
        - copy: email in copy (optional)
        - attachment: attachment (optional)
    """
    permission_classes = (IsAuthenticated, permissions.UserHasPermissionSendEmail,)
    serializer_class = SerializerEmailNotificationRiskAcceptance

    @extend_schema(
        request=SerializerEmailNotificationRiskAcceptance,
        responses={status.HTTP_201_CREATED: SerializerEmailNotificationRiskAcceptance},
    )
    def post(self, request):
        serializer = SerializerEmailNotificationRiskAcceptance(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        event = data.get("event", "risk_acceptance")
        recipients = data.get("recipients")
        title = data.get("title")
        template = data.get("template")
        copy_email = data.get("copy")
        subject = data.get("subject")
        message = data.get("message")
        description = data.get("description")
        url = data.get("url")
        icon = data.get("icon", "download")
        color_icon = data.get("color_icon", "#096C11")
        expiration_time_hours = data.get("expiration_time")
        product_id = data.get("product_id")
        engagement_id = data.get("engagement_id")
        finding_id = data.get("finding_id")
        risk_acceptance_id = data.get("risk_acceptance_id")
        enable_acceptance_risk_for_email = data.get("enable_acceptance_risk_for_email")
        long_risk_acceptance = data.get("long_risk_acceptance")
        attachment = request.FILES.get("attachment")
        risk_acceptance_eng_id = data.get("risk_acceptance_eng_id")

        if event == "url_report_finding":
            notification_kwargs = {
                "event": event,
                "subject": subject,
                "title": title,
                "description": description,
                "url": url,
                "recipients": recipients,
                "icon": icon,
                "color_icon": color_icon,
            }

            if expiration_time_hours:
                notification_kwargs["expiration_time"] = f"{expiration_time_hours} hours"

            encoded_url = encode_string(url)
            key = f"report_finding:{recipients[0]}:{encoded_url}"
            logger.debug(f"REPORT FINDING: calculate key url path {key}")
            expiration_time_seconds = expiration_time_hours * 3600 if expiration_time_hours else None
            cache.set(key, url, expiration_time_seconds)

            notification_kwargs["url"] = f"{settings.SITE_URL}/url_presigned/{encoded_url}"

            try:
                if product_id:
                    notification_kwargs["product"] = Product.objects.get(id=product_id)
                if engagement_id:
                    notification_kwargs["engagement"] = Engagement.objects.get(id=engagement_id)
                if finding_id:
                    notification_kwargs["finding"] = Finding.objects.get(id=finding_id)
            except ObjectDoesNotExist as exc:
                return http_response.bad_request(message=str(exc))

            try:
                create_notification(**notification_kwargs)
                return http_response.ok(message="Report download notification sent successfully")
            except Exception as exc:
                logger.exception("Error sending report download notification")
                return http_response.bad_request(message=f"Error sending notification: {exc}")
        
        attachment_data = None
        attachment_name = None
        attachment_content_type = None
        
        if attachment:
            attachment_data = attachment.read()
            attachment_name = attachment.name
            attachment_content_type = attachment.content_type
        
        from dojo.api_v2.notifications.helper import send_risk_acceptance_email_task
        send_risk_acceptance_email_task(
            recipients=recipients,
            subject=subject,
            message=message,
            copy_email=copy_email if copy_email else None,
            attachment_data=attachment_data,
            attachment_name=attachment_name,
            attachment_content_type=attachment_content_type,
            risk_acceptance_id=risk_acceptance_id,
            risk_acceptance_eng_id=risk_acceptance_eng_id,
            long_risk_acceptance=long_risk_acceptance,
            enable_acceptance_risk_for_email=enable_acceptance_risk_for_email,
            template=template,
        )

        if risk_acceptance_id:
            risk_acceptance = Risk_Acceptance.objects.get(id=risk_acceptance_id)
        elif risk_acceptance_eng_id:
            risk_acceptance = RiskAcceptanceEngagement.objects.get(id=risk_acceptance_eng_id)

            system_user = get_user(settings.SYSTEM_USER)
            risk_acceptance.add_note(
                f"Email notification send to {recipients} successfully, Message: " + (message if message else "No message provided"),
                author=system_user
            )

        return http_response.ok(
            message="Risk acceptance email sent successfully")


