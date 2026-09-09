from datetime import datetime

from rest_framework import serializers

from dojo.api_v2.cross_approval.models import (
    CrossApprovalDiscussion,
    CrossApprovalExclusion,
    CrossApprovalRequest,
    CrossApprovalRequestLog,
)
from dojo.api_v2.serializers import UserStubSerializer


def parse_cross_approval_date(value):
    if isinstance(value, str):
        for date_format in ("%d%m%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
    raise serializers.ValidationError("Use DDMMYYYY or YYYY-MM-DD for dates.")


class CrossApprovalExclusionSerializer(serializers.ModelSerializer):
    exclusion_id = serializers.IntegerField(source="pk", read_only=True)
    id = serializers.CharField(source="vulnerability_id")
    where = serializers.CharField(default="all", allow_blank=True, required=False)
    component_type = serializers.CharField(default="image", required=False)
    component_values = serializers.ListField(
        child=serializers.CharField(), min_length=1, required=False
    )
    create_date = serializers.CharField()
    expired_date = serializers.CharField()

    class Meta:
        model = CrossApprovalExclusion
        fields = (
            "exclusion_id", "id", "where", "create_date", "expired_date", "expired_at", "priority",
            "severity", "hu", "reason", "component_type", "component_values",
        )
        read_only_fields = ("expired_at",)

    def to_internal_value(self, data):
        data = data.copy()
        if "cve_id" in data and "id" not in data:
            data["id"] = data["cve_id"]
        if "id" in data and "cve_id" in data and data["id"] != data["cve_id"]:
            raise serializers.ValidationError(
                {"cve_id": "cve_id must match id when both are provided."}
            )

        component = data.get("component")
        if isinstance(component, dict):
            if "type" in component:
                data["component_type"] = component["type"]
            if "values" in component:
                data["component_values"] = component["values"]

        return super().to_internal_value(data)

    def validate_create_date(self, value):
        return parse_cross_approval_date(value)

    def validate_where(self, value):
        return value.strip() or "all"

    def validate_expired_date(self, value):
        return parse_cross_approval_date(value)

    def validate(self, attrs):
        if attrs["expired_date"] < attrs["create_date"]:
            raise serializers.ValidationError("expired_date must not precede create_date.")

        if not attrs.get("component_values"):
            raise serializers.ValidationError(
                {"component": "component.values must include at least one value."}
            )

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["create_date"] = instance.create_date.strftime("%d%m%Y")
        data["expired_date"] = instance.expired_date.strftime("%d%m%Y")
        data["cve_id"] = data["id"]
        component_type = data.pop("component_type")
        component_values = data.pop("component_values")
        data["component"] = {
            "type": component_type,
            "values": component_values,
        }

        return data


class CrossApprovalRequestSerializer(serializers.ModelSerializer):
    created_by = UserStubSerializer(read_only=True)
    status_updated_by = UserStubSerializer(read_only=True)
    exclusions = CrossApprovalExclusionSerializer(many=True)
    owner = serializers.CharField(required=True)
    discussions = serializers.SerializerMethodField()
    logs = serializers.SerializerMethodField()

    class Meta:
        model = CrossApprovalRequest
        fields = (
            "id", "owner", "status", "created_at", "created_by", "status_updated_by",
            "status_updated_at", "exclusions", "discussions", "logs",
        )
        read_only_fields = (
            "id", "status", "created_at", "created_by", "status_updated_by",
            "status_updated_at",
        )

    def validate(self, attrs):
        exclusions = attrs.get("exclusions", [])
        owner = attrs.get("owner") or (self.instance.owner if self.instance else None)
        vulnerability_ids = [exclusion["vulnerability_id"] for exclusion in exclusions]
        duplicate_ids = {
            vulnerability_id for vulnerability_id in vulnerability_ids
            if vulnerability_ids.count(vulnerability_id) > 1
        }
        if duplicate_ids:
            raise serializers.ValidationError({
                "exclusions": f"Vulnerability ID {min(duplicate_ids)} is duplicated in this request.",
            })

        conflicts = CrossApprovalExclusion.objects.filter(
            vulnerability_id__in=vulnerability_ids,
            request__owner=owner,
        )
        if self.instance:
            conflicts = conflicts.exclude(request=self.instance)
        conflict = conflicts.select_related("request").first()
        if conflict:
            raise serializers.ValidationError({
                "exclusions": (
                    f"Vulnerability ID {conflict.vulnerability_id} already exists in request "
                    f"{conflict.request_id} ({conflict.request.status})."
                ),
            })
        return attrs

    def create(self, validated_data):
        exclusions = validated_data.pop("exclusions")
        request = CrossApprovalRequest.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        CrossApprovalExclusion.objects.bulk_create(
            [CrossApprovalExclusion(request=request, **exclusion) for exclusion in exclusions]
        )
        return request

    def get_discussions(self, instance):
        return CrossApprovalDiscussionSerializer(
            instance.discussions.all(), many=True, context=self.context
        ).data

    def get_logs(self, instance):
        return CrossApprovalRequestLogSerializer(instance.logs.all(), many=True).data

    def update(self, instance, validated_data):
        exclusions = validated_data.pop("exclusions", None)
        if exclusions is not None:
            instance.exclusions.all().delete()
            CrossApprovalExclusion.objects.bulk_create(
                [CrossApprovalExclusion(request=instance, **exclusion) for exclusion in exclusions]
            )
        instance.owner = validated_data.get("owner", instance.owner)
        instance.save(update_fields=["owner"])
        return instance


class CrossApprovalDiscussionSerializer(serializers.ModelSerializer):
    author = UserStubSerializer(read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = CrossApprovalDiscussion
        fields = ("id", "author", "content", "created_at", "updated_at", "is_mine")
        read_only_fields = ("id", "author", "created_at", "updated_at", "is_mine")

    def get_is_mine(self, instance):
        request = self.context.get("request")
        return bool(request and request.user == instance.author)


class CrossApprovalRequestLogSerializer(serializers.ModelSerializer):
    changed_by = UserStubSerializer(read_only=True)

    class Meta:
        model = CrossApprovalRequestLog
        fields = ("id", "previous_status", "current_status", "changed_by", "changed_at")