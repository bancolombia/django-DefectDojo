from django.urls import path

from dojo.api_v2.engine_participation.views import (
    DeleteHCParticipationRecordsAPIView,
    ReturnHCParticipationToPendingAPIView,
    RunHCEvaluationAPIView,
)

urlpatterns = [
    path(
        "api/v2/engine_participation/run-evaluation/",
        RunHCEvaluationAPIView.as_view(),
        name="api_hc_run_evaluation",
    ),
    path(
        "api/v2/engine_participation/delete-records/",
        DeleteHCParticipationRecordsAPIView.as_view(),
        name="api_hc_delete_records",
    ),
    path(
        "api/v2/engine_participation/<uuid:hc_id>/return-to-pending/",
        ReturnHCParticipationToPendingAPIView.as_view(),
        name="api_hc_return_to_pending",
    ),
]
