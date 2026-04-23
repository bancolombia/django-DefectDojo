import logging
import os
import mimetypes
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from dojo.api_v2.long_risk_acceptance.models import *
from dojo.api_v2.long_risk_acceptance.serializers import * 
from dojo.api_v2.views import DojoModelViewSet
from dojo.api_v2.utils import http_response
import dojo.api_v2.long_risk_acceptance.helper as helper_ra_engagement 
from dojo.authorization.roles_permissions import Permissions
from rest_framework.pagination import LimitOffsetPagination
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
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
from drf_spectacular import openapi as oa
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import json

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
    

    @extend_schema(
        methods=["GET"],
        responses=FindingRenderRuleSerializer(many=True),
        request=None,
    )
    @action(detail=True, methods=["get"])
    def render_rule(self, request, pk):
        ra_engagement = get_object_or_404(RiskAcceptanceEngagement, id=pk)
        query = helper_ra_engagement.render_rule(ra_engagement)
        page = self.paginate_queryset(query)
        serializer = FindingRenderRuleSerializer(page if page is not None else query, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return http_response.ok(serializer.data)
    

    @extend_schema(
        methods=["POST"],
        responses=status.HTTP_201_CREATED,
        request=None,
    )
    @action(detail=True, methods=["post"])
    def apply_rule(self, request, pk):
        ra_engagement = get_object_or_404(RiskAcceptanceEngagement, id=pk)
        helper_ra_engagement.apply_rule(ra_engagement)
        return http_response.ok()
   

    @extend_schema(
        methods=['POST'],
        request=ExpirationSerializer,
        responses={
            201: OpenApiResponse(
                response=None,
                description="Review Confirmed",
                examples=[],
        )},
    )
    @action(detail=True, methods=["post"])
    def apply_review(self, request, pk):
        ra_engagement = get_object_or_404(RiskAcceptanceEngagement, id=pk)
        helper_ra_engagement.apply_review(request, ra_engagement)
        return http_response.created(message="Review Confirmed")
    

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