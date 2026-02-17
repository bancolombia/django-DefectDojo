from django.urls import path
from dojo.api_v2.security_posture.views import SecurityPosture, ProductSecurityPosture

# Manager cache url

urlpatterns = [
    path("api/v2/security_posture/engagement",
         SecurityPosture.as_view(),
         name='security_posture'),
    path("api/v2/security_posture/product",
         ProductSecurityPosture.as_view(),
         name='product_security_posture'),
]
