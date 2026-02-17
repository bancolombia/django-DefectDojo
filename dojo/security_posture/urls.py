from django.urls import re_path
from dojo.security_posture import views

urlpatterns = [
    re_path(
        r"^engagement/security_posture/$",
        views.security_posture_view,
        name="security_posture_view"
    ),
    re_path(
        r"^product/security_posture/$",
        views.product_security_posture_view,
        name="product_security_posture_view"
    ),
]