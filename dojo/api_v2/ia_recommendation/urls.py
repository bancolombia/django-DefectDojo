from django.urls import path
from dojo.api_v2.ia_recommendation.views import IArecommendationApiView, IAremediationApiView

# Manager cache url

urlpatterns = [
    path("api/v2/ia_recommendation/<int:id>/", IArecommendationApiView.as_view(), name='ia_recommendation'),
    path("api/v2/ia_remediation/<int:test_id>/", IAremediationApiView.as_view(), name='ia_remediation'),
]
