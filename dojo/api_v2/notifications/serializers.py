from rest_framework import serializers


class SerializerEmailNotificationRiskAcceptance(serializers.Serializer):
    recipients = serializers.ListField(child=serializers.CharField(), required=True)
    copy = serializers.EmailField(required=False, allow_blank=True)
    subject = serializers.CharField(required=True, max_length=255)
    event = serializers.CharField(required=False, default="risk_acceptance")
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    message = serializers.CharField(required=False, allow_blank=True)
    template = serializers.CharField(required=False, allow_blank=True)
    is_async = serializers.BooleanField(required=False, default=True)
    long_risk_acceptance = serializers.BooleanField(default=True)
    risk_acceptance_id = serializers.IntegerField(required=False)
    enable_acceptance_risk_for_email = serializers.BooleanField(required=False, default=False) 
    risk_acceptance_eng_id = serializers.IntegerField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    url = serializers.URLField(required=False)
    icon = serializers.CharField(required=False, default="download", max_length=50)
    color_icon = serializers.CharField(required=False, default="#096C11", max_length=10)
    expiration_time = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    engagement_id = serializers.IntegerField(required=False, allow_null=True)
    finding_id = serializers.IntegerField(required=False, allow_null=True)


    def validate(self, attrs):
        event = attrs.get("event")
        ra_id = attrs.get("risk_acceptance_id")
        eng_id = attrs.get("risk_acceptance_eng_id")

        has_ra_id = ra_id is not None
        has_eng_id = eng_id is not None

        if has_ra_id and has_eng_id:
            raise serializers.ValidationError({
                "non_field_errors": [
                    "Provide only one: 'risk_acceptance_id' or 'risk_acceptance_eng_id', not both."
                ],
                "risk_acceptance_id": ["Cannot coexist with 'risk_acceptance_eng_id'."],
                "risk_acceptance_eng_id": ["Cannot coexist with 'risk_acceptance_id'."],
            })

        if event == "url_report_finding":
            if not attrs.get("title"):
                raise serializers.ValidationError({
                    "title": ["This field is required when event='url_report_finding'."],
                })
            if not attrs.get("url"):
                raise serializers.ValidationError({
                    "url": ["This field is required when event='url_report_finding'."],
                })

        return attrs
