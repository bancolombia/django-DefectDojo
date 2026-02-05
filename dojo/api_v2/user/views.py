import logging
from dojo.api_v2.utils import http_response
from django.shortcuts import get_object_or_404
from dojo.models import Finding
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.cache import cache
from dojo.api_v2.ia_recommendation.serializers import IaRecommendationSerializer
from dojo.api_v2.ia_recommendation.helper import get_ia_recommendation
from dojo.api_v2.api_error import ApiError
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from drf_spectacular.utils import (
    extend_schema,
)
from dojo.api_v2 import (
    permissions,
)
logger = logging.getLogger(__name__)

@method_decorator(ensure_csrf_cookie, name='get')
class CrfTokenView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses={status.HTTP_200_OK},
    )
    def get(self, request):
        token = get_token(request)
        response = {"csrftoken": token, "detail": "CSRF cookie set"}
        return http_response.ok(message="CSRF cookie set", data=response)
    