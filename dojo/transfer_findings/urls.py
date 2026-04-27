from django.urls import re_path, path
from dojo.transfer_findings import views

urlpatterns = [
    path(
        "transfer_finding/delete/",
        views.TransferFindingDeleteView.as_view(),
        name='view_tranferFinding_delete'
    ),
    path("transfer_finding/<int:pk>/edit/",
         views.TransferFindingUpdateView.as_view(),
         name="transferfinding_update_form"),

    path("view_details_transfer_finding/<int:pk>/",
            views.view_transfer_finding_v2,
         name="view_details_transfer_finding"),

    path("view_list_transfer_finding/<int:pk>/",
            views.view_list_transfer_finding_v2,
         name="view_list_transfer_finding")
]
