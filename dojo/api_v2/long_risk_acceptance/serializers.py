from rest_framework import serializers
from dojo.api_v2.long_risk_acceptance.models import RiskAcceptanceEngagement, RiskAcceptanceExclusionRule

class RiskAcceptanceEngagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAcceptanceEngagement
        fields = '__all__'


class RiskAcceptanceExclusionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAcceptanceExclusionRule
        fields = '__all__'