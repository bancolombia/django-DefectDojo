import logging

from celery.result import AsyncResult
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from dojo.api_v2.utils import http_response
from dojo.engine_participation.helpers import run_hc_participation_evaluation

logger = logging.getLogger(__name__)


class RunHCEvaluationAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={status.HTTP_200_OK: dict, status.HTTP_400_BAD_REQUEST: dict})
    def get(self, request):
        if not request.user.is_superuser and not request.user.is_staff:
            return http_response.custom_response(
                code=status.HTTP_403_FORBIDDEN,
                status="forbidden",
                message="Only staff or superuser can monitor HC evaluation tasks.",
                data={},
            )

        task_id = request.query_params.get("task_id")
        if not task_id:
            return http_response.bad_request(
                message="task_id query parameter is required.",
                data={},
            )

        task = AsyncResult(task_id)
        data = {
            "task_id": task_id,
            "state": task.state,
            "ready": task.ready(),
            "successful": task.successful() if task.ready() else None,
        }

        if task.ready():
            if task.successful():
                data["result"] = task.result
            else:
                data["error"] = str(task.result)

        return http_response.ok(
            message="HC evaluation task status retrieved successfully.",
            data=data,
        )

    @extend_schema(responses={status.HTTP_200_OK: dict, status.HTTP_202_ACCEPTED: dict})
    def post(self, request):
        if not request.user.is_superuser and not request.user.is_staff:
            return http_response.custom_response(
                code=status.HTTP_403_FORBIDDEN,
                status="forbidden",
                message="Only staff or superuser can run HC evaluation.",
                data={},
            )

        execution_mode = request.query_params.get("mode", "async").lower()

        try:
            if execution_mode == "sync":
                result = run_hc_participation_evaluation(user=request.user)
                return http_response.ok(
                    message="HC evaluation executed successfully.",
                    data=result,
                )

            from dojo.engine_participation.helpers import run_hc_participation_evaluation_async

            task = run_hc_participation_evaluation_async.delay(user_id=request.user.id)
            return http_response.accepted(
                message="HC evaluation scheduled successfully.",
                data={
                    "task_id": task.id,
                    "mode": "async",
                    "status_endpoint": "/api/v2/engine_participation/run-evaluation?task_id=" + task.id,
                },
            )

        except Exception as exc:
            logger.exception("HC evaluation API execution failed: %s", exc)
            return http_response.error(
                message=f"HC evaluation failed: {str(exc)}",
                data={},
            )
