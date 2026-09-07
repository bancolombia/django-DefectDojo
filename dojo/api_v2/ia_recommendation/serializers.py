from rest_framework import serializers


class IaRecommendationSerializer(serializers.Serializer):
    status = serializers.CharField(required=False)
    ia_recommendations = serializers.CharField(required=True)


class IaRemediationBulkRequestSerializer(serializers.Serializer):
    finding_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        required=False,
    )
