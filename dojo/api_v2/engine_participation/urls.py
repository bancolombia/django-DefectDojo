from django.urls import path

from dojo.api_v2.engine_participation.views import DeleteHCParticipationRecordsAPIView, RunHCEvaluationAPIView

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
]
