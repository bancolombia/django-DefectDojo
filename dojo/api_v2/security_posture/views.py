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
from dojo.api_v2.security_posture.helper import get_engagement_security_posture, get_product_security_posture, get_product_type_security_posture
from dojo.api_v2.security_posture.serializers import (
    EngagementRequestSecuritypostureSerializer,
    EngagementSecuritypostureSerializer,
    ProductRequestSecurityPostureSerializer,
    ProductSecurityPostureSerializer,
    ProductTypeRequestSecurityPostureSerializer,
    ProductTypeSecurityPostureSerializer
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


class EngagementSecurityPosture(GenericAPIView):
    permission_classes = (
        IsAuthenticated,
        permissions.UserHasEngagementPermission,)
    serializer_class = EngagementSecuritypostureSerializer
    pagination_class = LimitOffsetPagination

    @extend_schema(
        request=EngagementRequestSecuritypostureSerializer,
        responses={status.HTTP_200_OK: EngagementSecuritypostureSerializer},
    )
    def get(self, request):
        serializer = EngagementRequestSecuritypostureSerializer(
            data=request.query_params)
        if serializer.is_valid():
            engagement = serializer.validated_data.get("engagement_id", None)
            engagement_name = serializer.validated_data.get("engagement_name", None)
            response = get_engagement_security_posture(engagement, engagement_name)
            serializer_response = EngagementSecuritypostureSerializer(data=response)
            if serializer_response.is_valid():
                return http_response.ok(
                    message="Engagement Security Posture Retrieved",
                    data=serializer_response.data)
            else:
                logger.error(serializer_response.errors)
                return http_response.bad_request(
                    message="Invalid response data", data=serializer_response.errors)
        else:
            return http_response.bad_request(
                message="Invalid serializer", data=serializer.errors)


class ProductSecurityPosture(GenericAPIView):
    permission_classes = (
        IsAuthenticated,
        permissions.UserHasProductPermission,)
    serializer_class = ProductSecurityPostureSerializer
    pagination_class = LimitOffsetPagination

    @extend_schema(
        request=ProductRequestSecurityPostureSerializer,
        responses={status.HTTP_200_OK: ProductSecurityPostureSerializer},
    )
    def get(self, request):
        serializer = ProductRequestSecurityPostureSerializer(
            data=request.query_params)
        if serializer.is_valid():
            product = serializer.validated_data.get("product_id", None)
            product_name = serializer.validated_data.get("product_name", None)
            response = get_product_security_posture(product, product_name)
            serializer_response = ProductSecurityPostureSerializer(data=response)
            if serializer_response.is_valid():
                return http_response.ok(
                    message="Product Security Posture Retrieved",
                    data=serializer_response.data)
            else:
                logger.error(serializer_response.errors)
                return http_response.bad_request(
                    message="Invalid response data", data=serializer_response.errors)
        else:
            return http_response.bad_request(
                message="Invalid serializer", data=serializer.errors)
            
class ProductTypeSecurityPosture(GenericAPIView):
    permission_classes = (
        IsAuthenticated,
        permissions.UserHasProductPermission,)
    serializer_class = ProductTypeSecurityPostureSerializer
    pagination_class = LimitOffsetPagination

    @extend_schema(
        request=ProductTypeRequestSecurityPostureSerializer,
        responses={status.HTTP_200_OK: ProductTypeSecurityPostureSerializer},
    )
    def get(self, request):
        serializer = ProductTypeRequestSecurityPostureSerializer(
            data=request.query_params)
        if serializer.is_valid():
            product_type = serializer.validated_data.get("product_type_id", None)
            product_type_name = serializer.validated_data.get("product_type_name", None)
            response = get_product_type_security_posture(product_type, product_type_name)
            serializer_response = ProductTypeSecurityPostureSerializer(data=response)
            if serializer_response.is_valid():
                return http_response.ok(
                    message="Product Type Security Posture Retrieved",
                    data=serializer_response.data)
            else:
                logger.error(serializer_response.errors)
                return http_response.bad_request(
                    message="Invalid response data", data=serializer_response.errors)
        else:
            return http_response.bad_request(
                message="Invalid serializer", data=serializer.errors)
