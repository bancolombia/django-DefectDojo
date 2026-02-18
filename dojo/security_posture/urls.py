from django.urls import re_path
from dojo.security_posture import views

urlpatterns = [
    re_path(
        r"^engagement/security_posture/$",
        views.engagement_security_posture_view,
        name="engagement_security_posture_view"
    ),
    re_path(
        r"^product/security_posture/$",
        views.product_security_posture_view,
        name="product_security_posture_view"
    ),
]