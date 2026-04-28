from django.urls import path
from dojo.api_v2.risk_posture.views import EngagementRiskPosture, ProductRiskPosture, ProductTypeRiskPosture

# Manager cache url

urlpatterns = [
    path("api/v2/risk_posture/engagement",
         EngagementRiskPosture.as_view(),
         name='engagement_risk_posture'),
    path("api/v2/risk_posture/product",
         ProductRiskPosture.as_view(),
         name='product_risk_posture'),
    path("api/v2/risk_posture/product_type",
         ProductTypeRiskPosture.as_view(),
         name='product_type_risk_posture_events'),
]
