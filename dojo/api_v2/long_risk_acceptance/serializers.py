from rest_framework import serializers
from django.utils import timezone
from dojo.api_v2.long_risk_acceptance.models import RiskAcceptanceEngagement, RiskAcceptanceExclusionRule
from dojo.models import GeneralSettings

class RiskAcceptanceEngagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAcceptanceEngagement
        fields = '__all__'
    
    # def create(self, validated_data):
    #     # 1. asociar automaticamente un "accepted_by": "","reviewed_by": "",
    #     if value :=  GeneralSettings.get_value("GROUP_REVIEWER_LONGTERM_ACCEPTANCE", "Reviewer_Risk"):
    #         reviewed_user = get_users_for_group_by_role(value, "Risk")
    #     validated_data["accepted_by"] = get_review_by()
    #     validated_data["reviewed_by"] = get_reviewed_by()
    #     # 2. validar fecha de expiracion "expiration_date": "2026-02-10T09:03:33.799Z",
    #     if (validated_data["expiration_date"] > timezone.now()
    #         and validated_data["expiration_date"] < GeneralSettings.get_value("MAXIMUM_ACCEPTANCE_DATE") ):
    #         # paso validacion de fecha 

    #     validated_data["expiration_date"]

        # 3. resive un listado de engagement "engagement": 1,




class RiskAcceptanceExclusionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAcceptanceExclusionRule
        fields = '__all__'