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