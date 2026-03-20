from rest_framework import serializers


class SerializerEmailNotificationRiskAcceptance(serializers.Serializer):
    recipients = serializers.ListField(child=serializers.CharField(), required=True)
    copy = serializers.EmailField(required=False, allow_blank=True)
    subject = serializers.CharField(required=True, max_length=255)
    message = serializers.CharField(required=False, allow_blank=True)
    template = serializers.CharField(required=False, allow_blank=True)
    is_async = serializers.BooleanField(required=False, default=True)
    long_risk_acceptance = serializers.BooleanField(default=True)
    risk_acceptance_id = serializers.IntegerField(required=False)
    enable_acceptance_risk_for_email = serializers.BooleanField(required=False, default=False) 
    risk_acceptance_eng_id = serializers.IntegerField(required=False)


    def validate(self, attrs):
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

        return attrs
