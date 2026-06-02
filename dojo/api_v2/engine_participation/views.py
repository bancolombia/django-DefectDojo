import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from dojo.api_v2.utils import http_response
from dojo.engine_participation.helpers import (
    get_active_hc_evaluation_run,
    run_hc_participation_evaluation_task,
)
from dojo.engine_participation.models import HCEvaluationRun

logger = logging.getLogger(__name__)


class RunHCEvaluationAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={status.HTTP_202_ACCEPTED: dict})
    def post(self, request):
        if not request.user.is_superuser and not request.user.is_staff:
            return http_response.custom_response(
                code=status.HTTP_403_FORBIDDEN,
                status="forbidden",
                message="Only staff or superuser can run HC evaluation.",
                data={},
            )

        try:
            active_run = get_active_hc_evaluation_run()

            if active_run:
                return http_response.accepted(
                    message="An HC evaluation is already running.",
                    data={
                        "run_id": str(active_run.id),
                        "status": active_run.status,
                        "task_id": active_run.celery_task_id,
                    },
                )

            run = HCEvaluationRun.objects.create(
                status=HCEvaluationRun.STATUS_PENDING,
                triggered_by=request.user,
            )

            task = run_hc_participation_evaluation_task.delay(
                run_id=str(run.id),
                user_id=request.user.id,
            )
            run.celery_task_id = task.id
            run.save(update_fields=["celery_task_id"])

            return http_response.accepted(
                message="HC evaluation queued successfully.",
                data={
                    "run_id": str(run.id),
                    "status": run.status,
                    "task_id": run.celery_task_id,
                },
            )
        except Exception as exc:
            logger.exception("HC evaluation API execution failed: %s", exc)
            return http_response.error(
                message=f"HC evaluation failed: {str(exc)}",
                data={},
            )
