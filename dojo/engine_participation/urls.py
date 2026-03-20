from django.urls import re_path
from dojo.engine_participation import views

urlpatterns = [
    re_path(
        r"^engine_participation/hc_participations$",
        views.hc_participations,
        name="hc_participations"
    ),
    re_path(
        r"^engine_participation/(?P<hcid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
        views.show_hc_participation,
        name="hc_participation"
    ),
    re_path(
        r"^engine_participation/(?P<hcid>[\w-]+)/add-discussion/$",
        views.add_hc_discussion,
        name="add_hc_discussion"
    ),
    re_path(
        r"^engine_participation/(?P<hcid>[\w-]+)/delete-discussion/(?P<did>\d+)/$",
        views.delete_hc_discussion,
        name="delete_hc_discussion"
    ),
    re_path(
        r"^engine_participation/(?P<hcid>[\w-]+)/review/$",
        views.review_hc_participation,
        name="review_hc_participation"
    ),
    re_path(
        r"^engine_participation/(?P<hcid>[\w-]+)/approve/$",
        views.approve_hc_participation_request,
        name="approve_hc_participation"
    ),
    re_path(
        r"^engine_participation/(?P<hcid>[\w-]+)/reject/$",
        views.reject_hc_participation_request,
        name="reject_hc_participation"
    ),
    re_path(
        r"^engine_participation/run-evaluation/$",
        views.run_hc_evaluation,
        name="run_hc_evaluation"
    ),
]
