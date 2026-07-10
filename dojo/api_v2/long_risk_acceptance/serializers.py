import logging
from rest_framework import serializers
from datetime import timedelta
from django.utils import timezone
from dojo.authorization.roles_permissions import Permissions
from dojo.api_v2.long_risk_acceptance.models import RiskAcceptanceEngagement, RiskAcceptanceExclusionRule
from dojo.group.queries import get_users_for_group, get_users_for_group_by_role
from dojo.utils import get_product, user_is_contacts
from dojo.group.queries import users_with_permissions_to_approve_long_term_findings
from dojo.authorization.authorization import user_has_permission, user_has_global_permission
from dojo.authorization.authorization import user_has_permission, user_has_global_permission
from tagulous.models import TagField
from dojo.models import GeneralSettings, Engagement, Dojo_User, Product, Finding 
from dojo.api_v2.serializers import EngagementSerializer, UserStubSerializer, NoteSerializer
from dojo.api_v2 import validators
from dojo.models import models
logger = logging.getLogger(__name__)

class EngagementSerializerRiskLongAcceptance(serializers.ModelSerializer):

    class Meta:
        model = Engagement
        fields = ["id", "name"]

class ProductSerializerRisLongAcceptance(serializers.ModelSerializer):

    class Meta:
        model = Product
        fields = ["id", "name"]


class FindingRenderRuleSerializer(serializers.ModelSerializer):

    class Meta:
        model = Finding
        fields = ["id", "priority", "cve", "risk_status"]


class RiskAcceptanceExclusionRuleSerializers(serializers.ModelSerializer):
    class Meta:
        model = RiskAcceptanceExclusionRule 
        fields = "__all__"

class RiskAcceptanceEngagementRequestSerializer(serializers.Serializer):
    CHOICES = [
        ("accept", "accept"),
        ("reject", "reject"),
        ("review", "review"),
    ]
    event = serializers.ChoiceField(required=False, choices=CHOICES)


class ExpirationSerializer(serializers.Serializer):
    expiration_date = serializers.DateField()
    
class LongRiskAcceptanceToNotesSerializer(serializers.Serializer):
    long_risk_acceptance_id = serializers.PrimaryKeyRelatedField(
        queryset=RiskAcceptanceEngagement.objects.all(), many=False, allow_null=True,
    )
    notes = NoteSerializer(many=True)

class RiskAcceptanceEngagementSerializer(serializers.ModelSerializer):
    description = serializers.CharField(
        validators=[validators.valid_chars_validator],
    )
    engagements_id = serializers.PrimaryKeyRelatedField(queryset=Engagement.objects.all(), many=True, source="engagement_set", required=True, write_only=True)
    engagements = EngagementSerializerRiskLongAcceptance(read_only=True, source="engagement_set", many=True) 
    accepted_by_id = serializers.PrimaryKeyRelatedField(source="accepted_by", queryset=Dojo_User.objects.all(), many=False, required=False, write_only=True)
    accepted_by = serializers.CharField(read_only=True)
    reviewed_by_id = serializers.PrimaryKeyRelatedField(source="reviewed_by", queryset=Dojo_User.objects.all(), many=False, required=True, write_only=True)
    reviewed_by = serializers.CharField(read_only=True)
    rules = RiskAcceptanceExclusionRuleSerializers(read_only=True, source="riskacceptanceexclusionrule_set", many=True)
    owner_id = serializers.PrimaryKeyRelatedField(source="owner", queryset=Dojo_User.objects.all(), many=False, required=False, write_only=True)
    owner = UserStubSerializer(read_only=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), many=False, required=True)
    notes = NoteSerializer(many=True, read_only=True)
    class Meta:
        model = RiskAcceptanceEngagement
        fields = '__all__'
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['permissions'] = []
        risk_acceptance_eng = RiskAcceptanceEngagement.objects.get(id=representation.get("id"))
        all_permissions = [
            Permissions.Long_Risk_Acceptance_Eng_Add,
            Permissions.Long_Risk_Acceptance_Eng_Edit,
            Permissions.Long_Risk_Acceptance_Eng_Delete,
            Permissions.Long_Risk_Acceptance_Eng_View,
            Permissions.Risk_Acceptance_Eng_Render,
            Permissions.Risk_Acceptance_Eng_Review,
            Permissions.Risk_Acceptance_Eng_Reject,
            Permissions.Risk_Acceptance_Eng_Note_View,
            Permissions.Risk_Acceptance_Eng_Note_Delete,
            Permissions.Risk_Acceptance_Eng_Note_Edit,
            Permissions.Risk_Acceptance_Eng_Note_Add,
            Permissions.Risk_Acceptance_Send_Email
            ]
        user = self.context["request"].user
        for permission in all_permissions:
            if user.is_superuser:
                representation['permissions'].append(permission.name)

            elif user_has_global_permission(user, permission):
                representation['permissions'].append(permission.name)

            elif user_is_contacts(user, risk_acceptance_eng.product):
                representation['permissions'].append(permission.name)

            elif user_has_permission(
                    user,
                    risk_acceptance_eng,
                    permission):
                    if permission == Permissions.Long_Risk_Acceptance_Eng_View:
                        representation['permissions'].append(permission.name)

        return representation

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        engagements = validated_data.pop("engagement_set")
        if value := GeneralSettings.get_value("GROUP_REVIEWER_LONGTERM_ACCEPTANCE", "Reviewer_Risk"):
            users = get_users_for_group_by_role(value, "Risk")
            if not validated_data["reviewed_by"] in users: 
                raise serializers.ValidationError({
                "reviewed_by": f"This user nreviewed_by_idot is valid"
            })

        user_reviewers = get_users_for_group_by_role("Reviewer_Risk", "Risk")
        if not validated_data["reviewed_by"] in user_reviewers:
            raise serializers.ValidationError({
                "accepted_by": f"This user not is valid for reviewer"
            })

        validated_data["reviewed_by"] = validated_data["reviewed_by"].username
        exp_date = validated_data["expiration_date"]
        now = timezone.now()
        sla_days = GeneralSettings.get_value("SLA_MAXIMUM_ACCEPTANCE_DAYS", 360)
        upper_limit = now + timedelta(days=sla_days)

        if not (exp_date > now and exp_date < upper_limit):
            raise serializers.ValidationError({
                "expiration_date": f"The date must be greater than now and less than {sla_days} days from today"
            })
        instance = RiskAcceptanceEngagement.objects.create(**validated_data)
        if engagements:
            instance.engagement_set.set(engagements)

        return instance

        
class RiskAcceptanceExclusionRuleSerializer(serializers.ModelSerializer):
    ra_engagement = serializers.PrimaryKeyRelatedField(queryset=RiskAcceptanceEngagement.objects.all(), many=False)
    title = serializers.CharField(required=True)
    include = serializers.JSONField(required=False, read_only=True, source="filters")
    filters = serializers.JSONField(required=False, write_only=True)


    class Meta:
        model = RiskAcceptanceExclusionRule
        fields = [
            "id",
            "ra_engagement",
            "title",
            "include",
            "filters",
            "exclusions",
        ]



