import logging
import os
import mimetypes
from rest_framework.decorators import action
from rest_framework import status
from dojo.models import RiskAcceptanceEngagement
from rest_framework.permissions import IsAuthenticated
from dojo.api_v2.long_risk_acceptance.models import *
from dojo.api_v2.long_risk_acceptance.serializers import * 
from dojo.api_v2 import serializers
from dojo.api_v2.views import DojoModelViewSet
from dojo.api_v2.utils import http_response
import dojo.api_v2.long_risk_acceptance.helper as helper_ra_engagement 
from dojo.authorization.roles_permissions import Permissions
from rest_framework.pagination import LimitOffsetPagination
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse, Http404, HttpResponse
from dojo.api_v2.api_error import ApiError
from dojo.api_v2.long_risk_acceptance.notifications import Notification
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

    def create(self, request, *args, **kwargs):
        serializer = RiskAcceptanceEngagementSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            instance = serializer.save()
            Notification.risk_acceptance_request(long_risk_acceptance=instance)
            return http_response.ok(
                message="Long Risk acceptance Created Successfully",
                data=RiskAcceptanceEngagementSerializer(instance, context={"request": request}).data
            )
        else:
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
        if query:
            page = self.paginate_queryset(query)
            serializer = FindingRenderRuleSerializer(page if page is not None else query, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(query, many=True)
        return http_response.ok(data=serializer.data)
    

    @extend_schema(
        methods=["POST"],
        responses=status.HTTP_201_CREATED,
        request=None,
    )
    @action(detail=True, methods=["post"])
    def apply_rule(self, request, pk):
        ra_engagement = get_object_or_404(RiskAcceptanceEngagement, id=pk)
        try:
            helper_ra_engagement.async_apply_rule_long_risk_acceptance.apply_async(
                args=(ra_engagement.id, request.user.id,))
            return http_response.ok(message="Render Rule Applied")
        except Exception as e:
            return http_response.error(
                message="Validation error occurred. ", data=str(e)
            )

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


    @action(
                methods=["POST"],
                detail=True,
                parser_classes=[MultiPartParser, FormParser]
        )
    def upload_file(self, request, pk=None):
        long_risk_acceptance = get_object_or_404(RiskAcceptanceEngagement, id=pk)
        if "file" not in request.FILES:
            return http_response.bad_request(message="File not found")
        uploaded_file = request.FILES["file"]
        long_risk_acceptance.path = uploaded_file
        long_risk_acceptance.save()
        return http_response.ok(message="File uploaded succesfully")
    
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="long_risk_acceptance_id",
                type=OpenApiTypes.INT,
                description="Long Risk Acceptance id",
                required=True,
            ),
        ],
    )
    @action(detail=False, methods=["get"], url_path="download_file")
    def download_file(self, request, *args, **kwargs):
        """
        GET /.../download_file/?long_risk_acceptance_id=<id>
        Returns the file attached to the given long risk acceptance as a downloadable response.
        """
        long_risk_acceptance_id = request.query_params.get("long_risk_acceptance_id") or request.query_params.get("long_risk_acceptance_id")
        if not long_risk_acceptance_id:
            return http_response.error(message="Missing 'long_risk_acceptance_id' query parameter.", data=None)

        long_risk_acceptance_obj = get_object_or_404(RiskAcceptanceEngagement, pk=long_risk_acceptance_id)

        file = long_risk_acceptance_obj.path
        if not file:
            raise ApiError.not_found(contex="File not fonud")

        try:
            file_handle = file.open("rb")
        except Exception as e:
            raise ApiError.internal_server_error(contex="Unable to open file: " + str(e))

        filename = os.path.basename(file.name)
        content_type, _ = mimetypes.guess_type(filename)
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
            content_type=content_type or "application/octet-stream"
            )
        return response
    
    @extend_schema(
        methods=["GET"],
        responses={
            status.HTTP_200_OK: serializers.AddNewNoteOptionSerializer,
        },
    )
    @extend_schema(
        methods=["POST"],
        request=serializers.AddNewNoteOptionSerializer,
        responses={status.HTTP_201_CREATED: serializers.NoteSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        long_risk_acceptance = self.get_object()
        if request.method == "POST":
            new_note = serializers.AddNewNoteOptionSerializer(
                data=request.data,
            )
            if new_note.is_valid():
                entry = new_note.validated_data["entry"]
                private = new_note.validated_data.get("private", False)
                note_type = new_note.validated_data.get("note_type", None)
            else:
                return Response(
                    new_note.errors, status=status.HTTP_400_BAD_REQUEST,
                )

            notes = long_risk_acceptance.note.filter(note_type=note_type).first()
            if notes and note_type and note_type.is_single:
                return Response("Only one instance of this note_type allowed on an engagement.", status=status.HTTP_400_BAD_REQUEST)

            author = request.user
            note = Notes(
                entry=entry,
                author=author,
                private=private,
                note_type=note_type,
            )
            note.save()
            long_risk_acceptance.note.add(note)

            serialized_note = serializers.NoteSerializer(
                {"author": author, "entry": entry, "private": private},
            )
            return Response(
                serialized_note.data, status=status.HTTP_201_CREATED,
            )
        notes = long_risk_acceptance.note.all()

        serialized_notes = serializers.TransferFindingToNotesSerializer(
            {"engagement_id": long_risk_acceptance, "notes": notes},
        )
        return Response(serialized_notes.data, status=status.HTTP_200_OK)

    

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