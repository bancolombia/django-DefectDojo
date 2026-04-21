from django.urls import path

from dojo.api_v2.engine_participation.views import RunHCEvaluationAPIView

urlpatterns = [
    path(
        "api/v2/engine_participation/run-evaluation",
        RunHCEvaluationAPIView.as_view(),
        name="api_hc_run_evaluation",
    ),
]
