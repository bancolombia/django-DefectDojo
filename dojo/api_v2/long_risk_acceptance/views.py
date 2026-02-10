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
        "engagement",
        "product",
    ] 
    pagination_class = LimitOffsetPagination

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
        "engagement",
    ]
    pagination_class = LimitOffsetPagination