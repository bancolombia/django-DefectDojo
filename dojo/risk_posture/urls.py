from django.urls import re_path
from dojo.risk_posture import views

urlpatterns = [
    re_path(
        r"^engagement/risk_posture/engagement/?$",
        views.engagement_risk_posture_view,
        name="engagement_risk_posture_view"
    ),
    re_path(
        r"^product/risk_posture/product/?$",
        views.product_risk_posture_view,
        name="product_risk_posture_view"
    ),
    re_path(
        r"^product_type/risk_posture/product_type/?$",
        views.product_type_risk_posture_view,
        name="product_type_risk_posture_view"
    ),
]