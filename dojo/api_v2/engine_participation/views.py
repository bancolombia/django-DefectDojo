import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from dojo.api_v2.utils import http_response
from dojo.engine_participation.helpers import run_hc_participation_evaluation

logger = logging.getLogger(__name__)


class RunHCEvaluationAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={status.HTTP_200_OK: dict})
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
