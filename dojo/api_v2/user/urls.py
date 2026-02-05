from django.urls import path
from dojo.api_v2.user.views import CrfTokenView

# Manager cache url

urlpatterns = [
    path("api/v2/csrf_token/", CrfTokenView.as_view(), name='csrf_token'),
]
