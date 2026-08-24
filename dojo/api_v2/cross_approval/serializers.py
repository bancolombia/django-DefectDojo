from datetime import datetime

from rest_framework import serializers

from dojo.api_v2.cross_approval.models import CrossApprovalExclusion, CrossApprovalRequest
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
    id = serializers.CharField(source="vulnerability_id")
    cve_id = serializers.CharField(required=False, allow_blank=True, default="")
    x86_image_name = serializers.ListField(
        source="image_names", child=serializers.CharField(), min_length=1
    )
    create_date = serializers.CharField()
    expired_date = serializers.CharField()

    class Meta:
        model = CrossApprovalExclusion
        fields = (
            "id", "cve_id", "where", "create_date", "expired_date", "priority",
            "severity", "hu", "reason", "x86_image_name",
        )

    def to_internal_value(self, data):
        data = data.copy()
        if "x86.image.name" in data and "x86_image_name" not in data:
            data["x86_image_name"] = data.pop("x86.image.name")
        return super().to_internal_value(data)

    def validate_create_date(self, value):
        return parse_cross_approval_date(value)

    def validate_expired_date(self, value):
        return parse_cross_approval_date(value)

    def validate(self, attrs):
        if attrs["expired_date"] < attrs["create_date"]:
            raise serializers.ValidationError("expired_date must not precede create_date.")
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["create_date"] = instance.create_date.strftime("%d%m%Y")
        data["expired_date"] = instance.expired_date.strftime("%d%m%Y")
        data["x86.image.name"] = data.pop("x86_image_name")
        return data


class CrossApprovalRequestSerializer(serializers.ModelSerializer):
    created_by = UserStubSerializer(read_only=True)
    status_updated_by = UserStubSerializer(read_only=True)
    exclusions = CrossApprovalExclusionSerializer(many=True)
    type = serializers.CharField(default="x86", required=False)

    class Meta:
        model = CrossApprovalRequest
        fields = (
            "id", "type", "status", "created_at", "created_by", "status_updated_by",
            "status_updated_at", "exclusions",
        )
        read_only_fields = (
            "id", "status", "created_at", "created_by", "status_updated_by",
            "status_updated_at",
        )

    def validate(self, attrs):
        exclusions = attrs.get("exclusions", [])
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
            vulnerability_id__in=vulnerability_ids
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

    def update(self, instance, validated_data):
        exclusions = validated_data.pop("exclusions", None)
        if exclusions is not None:
            instance.exclusions.all().delete()
            CrossApprovalExclusion.objects.bulk_create(
                [CrossApprovalExclusion(request=instance, **exclusion) for exclusion in exclusions]
            )
        instance.type = validated_data.get("type", instance.type)
        instance.save(update_fields=["type"])
        return instance