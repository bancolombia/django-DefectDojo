from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

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
from dojo.api_v2.cross_approval.permissions import IsCrossApprovalMaintainer
from dojo.api_v2.cross_approval.serializers import (
    CrossApprovalDiscussionSerializer,
    CrossApprovalRequestSerializer,
)


class CrossApprovalRequestViewSet(ModelViewSet):
    queryset = CrossApprovalRequest.objects.select_related(
        "created_by", "status_updated_by"
    ).prefetch_related("exclusions", "discussions__author", "logs__changed_by")
    serializer_class = CrossApprovalRequestSerializer
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.action in {"update", "partial_update", "destroy", "approve", "reject", "expire", "expire_exclusion", "reopen_exclusion"}:
            return [IsAuthenticated(), IsCrossApprovalMaintainer()]
        return super().get_permissions()

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
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["get", "post"])
    def discussions(self, request, pk=None):
        instance = self.get_object()
        if request.user != instance.created_by and not IsCrossApprovalMaintainer().has_permission(request, self):
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
            instance.delete()