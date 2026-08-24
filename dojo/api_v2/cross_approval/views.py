from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from dojo.api_v2.cross_approval.models import CrossApprovalExclusion, CrossApprovalRequest
from dojo.api_v2.cross_approval.permissions import IsCrossApprovalMaintainer
from dojo.api_v2.cross_approval.serializers import CrossApprovalRequestSerializer


class CrossApprovalRequestViewSet(ModelViewSet):
    queryset = CrossApprovalRequest.objects.select_related(
        "created_by", "status_updated_by"
    ).prefetch_related("exclusions")
    serializer_class = CrossApprovalRequestSerializer
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.action in {"update", "partial_update", "destroy", "approve", "reject"}:
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

    def _set_status(self, request, status):
        instance = self.get_object()
        instance.status = status
        instance.status_updated_by = request.user
        instance.status_updated_at = timezone.now()
        instance.save(update_fields=["status", "status_updated_by", "status_updated_at"])
        return Response(self.get_serializer(instance).data)