import logging
from dojo.api_v2.utils import http_response
from django.shortcuts import get_object_or_404
from dojo.models import Finding, Test
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.cache import cache
from dojo.api_v2.ia_recommendation.serializers import IaRecommendationSerializer, IaRemediationBulkRequestSerializer
from dojo.api_v2.ia_recommendation.helper import async_get_ia_recommendation
from dojo.api_v2.api_error import ApiError
from drf_spectacular.utils import (
    extend_schema,
)
from dojo.api_v2 import (
    permissions,
)
logger = logging.getLogger(__name__)


class IArecommendationApiView(APIView):
    permission_classes = (IsAuthenticated,
                          permissions.UserHasFindingPermission,)
    serializer_class = IaRecommendationSerializer

    @extend_schema(
        responses={status.HTTP_200_OK: IaRecommendationSerializer},
    )
    def get(self, request, id):
        finding = get_object_or_404(Finding, pk=id)
        ia_recommendation = async_get_ia_recommendation(str(finding.id), request.user)
        return ia_recommendation


class IAremediationApiView(APIView):
    permission_classes = (IsAuthenticated,
                          permissions.UserHasTestPermission,)
    serializer_class = IaRecommendationSerializer

    @extend_schema(
        request=IaRemediationBulkRequestSerializer,
        responses={status.HTTP_200_OK: IaRecommendationSerializer},
    )
    def post(self, request, test_id):
        test = get_object_or_404(Test, pk=test_id)
        serializer = IaRemediationBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True) 
        findings = str(list(test.finding_set.filter(active=True, duplicate=False).values_list('id', flat=True))).replace("[", "").replace("]", "").replace(" ", "")
        async_get_ia_recommendation.apply_async(args=[findings, request.user, False])
        return http_response.ok(message="OK", data={"findings": findings})
