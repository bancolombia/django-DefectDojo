from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from dojo.api_v2.mixins import DeletePreviewModelMixin
from dojo.api_v2.cross_approval.helpers import (
    apply_request_exclusions,
    expire_cross_approval_exclusion,
    expire_request_exclusions,
    log_status_change,
    notify_request_status,
    reopen_cross_approval_exclusion,
    revert_cross_approval_exclusion,
)
from dojo.api_v2.cross_approval.models import CrossApprovalDiscussion, CrossApprovalExclusion, CrossApprovalRequest
from dojo.api_v2.cross_approval.permissions import IsCrossApprovalReviewer, IsCrossApprovalSubmitter
from dojo.api_v2.cross_approval.serializers import (
    CrossApprovalExclusionSerializer,
    CrossApprovalDiscussionSerializer,
    CrossApprovalRequestSerializer,
)


class CrossApprovalRequestViewSet(DeletePreviewModelMixin, ModelViewSet):
    queryset = CrossApprovalRequest.objects.select_related(
        "created_by", "status_updated_by"
    ).prefetch_related("exclusions", "discussions__author", "logs__changed_by")
    serializer_class = CrossApprovalRequestSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = super().get_queryset()
        request_id = self.request.query_params.get("id") if self.request else None
        vulnerability_id = self.request.query_params.get("cve") if self.request else None
        status = self.request.query_params.get("status") if self.request else None

        if request_id:
            queryset = queryset.filter(pk=request_id) if request_id.isdigit() else queryset.none()
        if vulnerability_id:
            queryset = queryset.filter(exclusions__vulnerability_id__icontains=vulnerability_id)
        if status:
            queryset = queryset.filter(status=status)
        return queryset.distinct()

    def get_permissions(self):
        if self.action in {"approve", "reject"}:
            return [IsAuthenticated(), IsCrossApprovalReviewer()]
        if self.action in {"create", "update", "partial_update", "destroy", "expire", "expire_exclusion", "reopen_exclusion"}:
            return [IsAuthenticated(), IsCrossApprovalSubmitter()]
        return super().get_permissions()

    def perform_create(self, serializer):
        instance = serializer.save()
        notify_request_status(
            instance,
            "cross_approval_created",
            f"Cross-approval request {instance.pk} created",
        )

    @action(detail=False, methods=["get"], url_path="validate-vulnerability-id")
    def validate_vulnerability_id(self, request):
        vulnerability_id = request.query_params.get("vulnerability_id", "").strip()
        if not vulnerability_id:
            return Response({"detail": "vulnerability_id is required."}, status=400)

        exclusions = CrossApprovalExclusion.objects.filter(
            vulnerability_id=vulnerability_id
        ).select_related("request")
        exclude_request_id = request.query_params.get("exclude_request_id")
        if exclude_request_id:
            exclusions = exclusions.exclude(request_id=exclude_request_id)

        conflicts = [
            {"request_id": exclusion.request_id, "status": exclusion.request.status}
            for exclusion in exclusions
        ]
        return Response({"vulnerability_id": vulnerability_id, "conflicts": conflicts})

    @action(detail=False, methods=["get"], url_path="base-images")
    def base_images(self, request):
        summaries = {}
        image_name_filter = request.query_params.get("image_name", "").strip().casefold()
        queryset = self.filter_queryset(self.get_queryset()).filter(status="approved").prefetch_related("exclusions")
        today = timezone.localdate()
        for cross_approval_request in queryset:
            for exclusion in cross_approval_request.exclusions.all():
                if not self._is_active_exclusion(exclusion, today):
                    continue
                for image_name in self._matching_image_names(exclusion, image_name_filter):
                    self._add_base_image_summary(summaries, cross_approval_request, exclusion, image_name)
        return Response(self._base_image_response(summaries))

    def _is_active_exclusion(self, exclusion, today):
        return not exclusion.expired_at and exclusion.expired_date >= today

    def _matching_image_names(self, exclusion, image_name_filter):
        image_names = set(exclusion.image_names or [])
        if not image_name_filter:
            return image_names
        return [
            image_name
            for image_name in image_names
            if image_name_filter in image_name.casefold()
        ]

    def _add_base_image_summary(self, summaries, cross_approval_request, exclusion, image_name):
        summary = summaries.setdefault(
            image_name,
            {
                "image_name": image_name,
                "type": cross_approval_request.type,
                "exclusion_count": 0,
                "vulnerability_exclusions": {},
            },
        )
        summary["exclusion_count"] += 1
        vulnerability_id = exclusion.vulnerability_id
        vulnerability_summary = summary["vulnerability_exclusions"].setdefault(
            vulnerability_id,
            {"vulnerability_id": vulnerability_id, "exclusions": []},
        )
        vulnerability_summary["exclusions"].append(
            CrossApprovalExclusionSerializer(exclusion).data
        )

    def _base_image_response(self, summaries):
        return [
            {
                **summary,
                "vulnerability_exclusions": list(summary["vulnerability_exclusions"].values()),
            }
            for summary in summaries.values()
        ]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._set_status(request, "approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._set_status(request, "rejected")

    @action(detail=True, methods=["post"])
    def expire(self, request, pk=None):
        instance = self.get_object()
        if instance.status != "approved":
            return Response({"detail": "Only approved requests can expire exclusions."}, status=400)
        expire_request_exclusions(instance)
        notify_request_status(
            instance,
            "cross_approval_expired",
            f"Cross-approval request {instance.pk} expired",
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"], url_path="expire-exclusion")
    def expire_exclusion(self, request, pk=None):
        instance = self.get_object()
        if instance.status != "approved":
            return Response({"detail": "Only exclusions on approved requests can expire."}, status=400)
        exclusion_id = request.data.get("exclusion_id")
        exclusion = instance.exclusions.filter(pk=exclusion_id).first()
        if not exclusion:
            return Response({"detail": "Exclusion not found on this request."}, status=404)
        expire_cross_approval_exclusion(exclusion, request.user)
        notify_request_status(
            instance,
            "cross_approval_expired",
            f"Cross-approval request {instance.pk} exclusion expired",
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="reopen-exclusion")
    def reopen_exclusion(self, request, pk=None):
        instance = self.get_object()
        if instance.status != "approved":
            return Response({"detail": "Only exclusions on approved requests can reopen."}, status=400)
        exclusion = instance.exclusions.filter(pk=request.data.get("exclusion_id")).first()
        if not exclusion:
            return Response({"detail": "Exclusion not found on this request."}, status=404)
        if not reopen_cross_approval_exclusion(exclusion, request.user):
            return Response({"detail": "Only manually expired, non-expired exclusions can reopen."}, status=400)
        notify_request_status(
            instance,
            "cross_approval_reopened",
            f"Cross-approval request {instance.pk} exclusion reopened",
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["get", "post"])
    def discussions(self, request, pk=None):
        instance = self.get_object()
        if request.method == "POST" and request.user != instance.created_by and not IsCrossApprovalReviewer().has_permission(request, self):
            return Response({"detail": "Only the requester or a maintainer can access discussions."}, status=403)
        if request.method == "GET":
            return Response(CrossApprovalDiscussionSerializer(
                instance.discussions.all(), many=True, context={"request": request}
            ).data)
        serializer = CrossApprovalDiscussionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        discussion = serializer.save(request=instance, author=request.user)
        notify_request_status(instance, "cross_approval_discussion", f"New discussion on cross-approval request {instance.pk}")
        return Response(
            CrossApprovalDiscussionSerializer(discussion, context={"request": request}).data,
            status=201,
        )

    def _set_status(self, request, status):
        instance = self.get_object()
        if instance.status != "pending":
            return Response({"detail": "Only pending requests can be decided."}, status=400)
        previous_status = instance.status
        instance.status = status
        instance.status_updated_by = request.user
        instance.status_updated_at = timezone.now()
        instance.save(update_fields=["status", "status_updated_by", "status_updated_at"])
        log_status_change(instance, request.user, previous_status, status)
        if status == "approved":
            apply_request_exclusions(instance)
        notify_request_status(instance, f"cross_approval_{status}", f"Cross-approval request {instance.pk} {status}")
        return Response(self.get_serializer(instance).data)

    def perform_destroy(self, instance):
        with transaction.atomic():
            if instance.status == "approved":
                for exclusion in instance.exclusions.all():
                    revert_cross_approval_exclusion(exclusion)
            notify_request_status(
                instance,
                "cross_approval_deleted",
                f"Cross-approval request {instance.pk} deleted",
            )
            instance.delete()