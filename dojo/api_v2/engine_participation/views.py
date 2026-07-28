import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from dojo.api_v2.engine_participation.serializers import DeleteHCParticipationRecordsRequestSerializer
from dojo.api_v2.utils import http_response
from dojo.engine_participation.helpers import (
    delete_hc_participation_records_by_date_range,
    run_hc_participation_evaluation,
)

logger = logging.getLogger(__name__)


class RunHCEvaluationAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={status.HTTP_200_OK: dict})
    def post(self, request):
        if not request.user.is_superuser and not request.user.is_staff:
            return http_response.custom_response(
                code=status.HTTP_403_FORBIDDEN,
                status="forbidden",
                message="Only staff or superuser can run HC evaluation.",
                data={},
            )

        try:
            result = run_hc_participation_evaluation(user=request.user)
            return http_response.ok(
                message="HC evaluation executed successfully.",
                data=result,
            )
        except Exception as exc:
            logger.exception("HC evaluation API execution failed: %s", exc)
            return http_response.error(
                message=f"HC evaluation failed: {str(exc)}",
                data={},
            )


class DeleteHCParticipationRecordsAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = DeleteHCParticipationRecordsRequestSerializer

    @extend_schema(
        request=DeleteHCParticipationRecordsRequestSerializer,
        responses={status.HTTP_200_OK: dict},
    )
    def post(self, request):
        if not request.user.is_superuser and not request.user.is_staff:
            return http_response.custom_response(
                code=status.HTTP_403_FORBIDDEN,
                status="forbidden",
                message="Only staff or superuser can delete HC participation records.",
                data={},
            )

        serializer = DeleteHCParticipationRecordsRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return http_response.bad_request(
                message="'start_date' and 'end_date' must be valid dates in YYYY-MM-DD format.",
                data=serializer.errors,
            )

        start_date = serializer.validated_data["start_date"]
        end_date = serializer.validated_data["end_date"]

        try:
            result = delete_hc_participation_records_by_date_range(start_date, end_date)
            return http_response.ok(
                message="HC participation records deleted successfully.",
                data=result,
            )
        except ValueError as exc:
            return http_response.bad_request(message=str(exc), data={})
        except Exception as exc:
            logger.exception("HC participation records deletion failed: %s", exc)
            return http_response.error(
                message=f"HC participation records deletion failed: {str(exc)}",
                data={},
            )

