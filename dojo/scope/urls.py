from django.urls import re_path
from dojo.scope import views

urlpatterns = [
    re_path(
        r"^product/scope/(?P<product_id>\d+)$",
        views.scope_view,
        name="scope_view"
    )
]