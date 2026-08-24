from django.urls import re_path

from dojo.engine_tools.cross_approval_views import crossapproval_list


urlpatterns = [
    re_path(r"^cross-approval/list$", crossapproval_list, name="crossapproval_list"),
]