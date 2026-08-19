from django.urls import path
from dojo.long_risk_acceptance import views

urlpatterns = [
    path(
        "long_risk_acceptance/details/<int:pk>/",
        views.view_long_risk_acceptance_details,
        name='view_long_risk_acceptance_details'
    ),
    path(
        "long_risk_acceptance/list/",
        views.view_long_risk_acceptance_list,
        name='view_long_risk_acceptance_list'
    )
]
