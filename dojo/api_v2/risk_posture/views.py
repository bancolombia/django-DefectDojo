import logging
from collections import OrderedDict
from rest_framework.generics import GenericAPIView
from dojo.api_v2.utils import http_response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from django.core.cache import cache
from dojo.api_v2.risk_posture.helper import get_engagement_risk_posture, get_product_risk_posture, get_product_type_risk_posture
from dojo.api_v2.risk_posture.serializers import (
    EngagementRequestRiskpostureSerializer,
    EngagementRiskpostureSerializer,
    ProductRequestRiskPostureSerializer,
    ProductRiskPostureSerializer,
    ProductTypeRequestRiskPostureSerializer,
    ProductTypeRiskPostureSerializer
    )
from dojo.api_v2.api_error import ApiError
from dojo.models import Finding
from drf_spectacular.utils import (
    extend_schema,
)
from dojo.api_v2 import (
    permissions,
)
logger = logging.getLogger(__name__)


class EngagementRiskPosture(GenericAPIView):
    permission_classes = (
        IsAuthenticated,
        permissions.UserHasEngagementPermission,)
    serializer_class = EngagementRiskpostureSerializer
    pagination_class = LimitOffsetPagination

    @extend_schema(
        request=EngagementRequestRiskpostureSerializer,
        responses={status.HTTP_200_OK: EngagementRiskpostureSerializer},
    )
    def get(self, request):
        serializer = EngagementRequestRiskpostureSerializer(
            data=request.query_params)
        if serializer.is_valid():
            engagement = serializer.validated_data.get("engagement_id", None)
            engagement_name = serializer.validated_data.get("engagement_name", None)
            response = get_engagement_risk_posture(engagement, engagement_name)
            serializer_response = EngagementRiskpostureSerializer(data=response)
            if serializer_response.is_valid():
                return http_response.ok(
                    message="Engagement Risk Posture Retrieved",
                    data=serializer_response.data)
            else:
                logger.error(serializer_response.errors)
                return http_response.bad_request(
                    message="Invalid response data", data=serializer_response.errors)
        else:
            return http_response.bad_request(
                message="Invalid serializer", data=serializer.errors)


class ProductRiskPosture(GenericAPIView):
    permission_classes = (
        IsAuthenticated,
        permissions.UserHasProductPermission,)
    serializer_class = ProductRiskPostureSerializer
    pagination_class = LimitOffsetPagination

    @extend_schema(
        request=ProductRequestRiskPostureSerializer,
        responses={status.HTTP_200_OK: ProductRiskPostureSerializer},
    )
    def get(self, request):
        serializer = ProductRequestRiskPostureSerializer(
            data=request.query_params)
        if serializer.is_valid():
            product = serializer.validated_data.get("product_id", None)
            product_name = serializer.validated_data.get("product_name", None)
            response = get_product_risk_posture(product, product_name)
            serializer_response = ProductRiskPostureSerializer(data=response)
            if serializer_response.is_valid():
                return http_response.ok(
                    message="Product Risk Posture Retrieved",
                    data=serializer_response.data)
            else:
                logger.error(serializer_response.errors)
                return http_response.bad_request(
                    message="Invalid response data", data=serializer_response.errors)
        else:
            return http_response.bad_request(
                message="Invalid serializer", data=serializer.errors)
            
class ProductTypeRiskPosture(GenericAPIView):
    permission_classes = (
        IsAuthenticated,
        permissions.UserHasProductTypePermission,)
    serializer_class = ProductTypeRiskPostureSerializer
    pagination_class = LimitOffsetPagination

    @extend_schema(
        request=ProductTypeRequestRiskPostureSerializer,
        responses={status.HTTP_200_OK: ProductTypeRiskPostureSerializer},
    )
    def get(self, request):
        serializer = ProductTypeRequestRiskPostureSerializer(
            data=request.query_params)
        if serializer.is_valid():
            product_type = serializer.validated_data.get("product_type_id", None)
            product_type_name = serializer.validated_data.get("product_type_name", None)
            response = get_product_type_risk_posture(product_type, product_type_name)
            serializer_response = ProductTypeRiskPostureSerializer(data=response)
            if serializer_response.is_valid():
                return http_response.ok(
                    message="Product Type Risk Posture Retrieved",
                    data=serializer_response.data)
            else:
                logger.error(serializer_response.errors)
                return http_response.bad_request(
                    message="Invalid response data", data=serializer_response.errors)
        else:
            return http_response.bad_request(
                message="Invalid serializer", data=serializer.errors)
