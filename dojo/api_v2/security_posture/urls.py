from django.urls import path
from dojo.api_v2.security_posture.views import EngagementSecurityPosture, ProductSecurityPosture, ProductTypeSecurityPosture

# Manager cache url

urlpatterns = [
    path("api/v2/security_posture/engagement",
         EngagementSecurityPosture.as_view(),
         name='engagement_security_posture'),
    path("api/v2/security_posture/product",
         ProductSecurityPosture.as_view(),
         name='product_security_posture'),
    path("api/v2/security_posture/product_type",
         ProductTypeSecurityPosture.as_view(),
         name='product_type_security_posture_events'),
]
