import logging
import os
import mimetypes
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction, IntegrityError
from dojo.api_v2.pentesting.filter import InputFilter
from dojo.api_v2.long_risk_acceptance.models import *
from dojo.api_v2.long_risk_acceptance.serializers import * 
from dojo.api_v2.views import DojoModelViewSet
from dojo.api_v2.utils import http_response
from dojo.authorization.roles_permissions import Permissions
from rest_framework.pagination import LimitOffsetPagination
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse
from dojo.api_v2.api_error import ApiError
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    OpenApiTypes,
)
from dojo.api_v2 import (
    permissions,
    prefetch,
)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import json

from dojo.finding import serializer

logger = logging.getLogger(__name__)

class RiskAcceptanceEngagementViewSet(prefetch.PrefetchListMixin,
                             prefetch.PrefetchRetrieveMixin,
                             DojoModelViewSet):
    queryset = RiskAcceptanceEngagement.objects.all() 
    permission_classes = (IsAuthenticated,
                          permissions.UserHasLongRiskAcceptancePermission,)
    serializer_class = RiskAcceptanceEngagementSerializer 
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = [
        "id",
        "owner",
        "product",
    ] 
    pagination_class = LimitOffsetPagination

    def post(self, request, *args, **kwargs):
        try:
            serializer = RiskAcceptanceEngagementSerializer(request)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            return http_response.ok(
                message="Long Risk acceptance Created Successfully",
                data=RiskAcceptanceEngagementSerializer(instance).data
            )
        except Exception as e:
            logger.error(f"Validation error on POST long risk acceptance object")
            return http_response.error(
                message="Validation error occurred. ", data=serializer.errors)


@extend_schema(tags=["long_risk_acceptance"])
class RiskAcceptanceExclusionRuleViewSet(prefetch.PrefetchListMixin,
                             prefetch.PrefetchRetrieveMixin,
                             DojoModelViewSet):
    queryset = RiskAcceptanceExclusionRule.objects.all() 
    permission_classes = (IsAuthenticated,
                          permissions.UserHasLongRiskAcceptancePermission,)
    serializer_class = RiskAcceptanceExclusionRuleSerializer 
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = [
        "id",
    ]
    pagination_class = LimitOffsetPagination


    def post(self, request, *args, **kwargs):
        try:
            serializer = RiskAcceptanceExclusionRuleSerializer(request)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            return http_response.ok(
                message="Long Risk acceptance Rules Created Successfully",
                data=RiskAcceptanceExclusionRuleSerializer(instance).data
            )
        except Exception as e:
            logger.error(f"Validation error on POST long risk acceptance Rules")
            return http_response.error(
                message="Validation error occurred. ", data=serializer.errors)