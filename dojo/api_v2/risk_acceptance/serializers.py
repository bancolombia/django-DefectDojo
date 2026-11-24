from rest_framework import serializers
from dojo.api_v2.serializers import NoteSerializer, FindingSerializer
from dojo.models import Risk_Acceptance, Notes, Dojo_User, Finding, Engagement
from drf_spectacular.utils import extend_schema_field
from django.urls import reverse


class RiskAcceptanceToNotesSerializer(serializers.Serializer):
    risk_acceptance = serializers.PrimaryKeyRelatedField(
        queryset=Risk_Acceptance.objects.all(), many=False, allow_null=True,
    )
    notes = NoteSerializer(many=True)

class RiskAcceptanceRetriveSerializer(serializers.ModelSerializer):
    path = serializers.SerializerMethodField()
    name = serializers.CharField(required=True)
    long_term_acceptance = serializers.BooleanField(default=False)
    accepted_findings = FindingSerializer(many=True, read_only=True)
    severity = serializers.CharField(read_only=True)
    priority_classification = serializers.CharField(source="priority", read_only=True)
    recommendation = serializers.CharField(required=False)
    recommendation_details = serializers.CharField(required=False)
    decision = serializers.CharField(required=False)
    decision_details = serializers.CharField(required=False)
    accepted_by = serializers.CharField(read_only=True)
    reviewed_by = serializers.CharField(read_only=True)
    path = serializers.SerializerMethodField()
    engagement = serializers.PrimaryKeyRelatedField(read_only=True)
    engagement_name = serializers.CharField(source="engagement", read_only=True)
    product = serializers.PrimaryKeyRelatedField(read_only=True)
    product_name = serializers.CharField(source="engagement.product.name", read_only=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=Dojo_User.objects.all(), required=False)    
    owner_name = serializers.CharField(read_only=True, source="owner.username")
    status = serializers.CharField(read_only=True)
    reviewed_date = serializers.DateTimeField(read_only=True)
    accepted_date = serializers.DateTimeField(read_only=True)
    expiration_date = serializers.DateTimeField(required=False)
    expiration_date_warned = serializers.DateTimeField(read_only=True)
    expiration_date_handled = serializers.DateTimeField(read_only=True)
    reactivate_expired = serializers.BooleanField(read_only=True)
    restart_sla_expired = serializers.BooleanField(read_only=True)
    notes = serializers.PrimaryKeyRelatedField(many=True, queryset=Notes.objects.all(), required=False)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Risk_Acceptance
        fields = "__all__"

    @extend_schema_field(serializers.CharField())
    def get_path(self, obj):
        engagement = Engagement.objects.filter(
            risk_acceptance__id__in=[obj.id],
        ).first()
        path = "No proof has been supplied"
        if engagement and obj.filename() is not None:
            path = reverse(
                "download_risk_acceptance", args=(engagement.id, obj.id),
            )
            request = self.context.get("request")
            if request:
                path = request.build_absolute_uri(path)
        return path
