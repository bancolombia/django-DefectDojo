from unittest.mock import patch
from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from dojo.api_v2.cross_approval.serializers import (
    CrossApprovalExclusionSerializer,
    CrossApprovalRequestSerializer,
)
from dojo.api_v2.cross_approval.views import CrossApprovalRequestViewSet


class CrossApprovalExclusionSerializerTest(SimpleTestCase):
    def valid_payload(self):
        return {
            "id": "#sym:vulnerability_id",
            "where": "all",
            "create_date": "2026-08-23",
            "expired_date": "2026-08-24",
            "priority": "high",
            "severity": "medium",
            "hu": "HU-1",
            "reason": "Supplier exception",
            "x86.image.name": ["registry.example.com/base:1.0"],
        }

    def test_accepts_exclusion_without_cve_id(self):
        serializer = CrossApprovalExclusionSerializer(data=self.valid_payload())

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["vulnerability_id"], "#sym:vulnerability_id")
        self.assertEqual(serializer.validated_data["cve_id"], "")
        self.assertEqual(serializer.validated_data["image_names"], ["registry.example.com/base:1.0"])

    def test_rejects_expired_date_before_create_date(self):
        payload = self.valid_payload()
        payload["expired_date"] = "2026-08-22"
        serializer = CrossApprovalExclusionSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)


class CrossApprovalRequestSerializerTest(SimpleTestCase):
    def test_defaults_request_type_to_x86(self):
        with patch(
            "dojo.api_v2.cross_approval.serializers.CrossApprovalExclusion.objects.filter"
        ) as exclusions_filter:
            exclusions_filter.return_value.select_related.return_value.first.return_value = None
            serializer = CrossApprovalRequestSerializer(data={
                "exclusions": [CrossApprovalExclusionSerializerTest().valid_payload()],
            })

            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["type"], "x86")

    def test_allows_priority_and_severity_to_be_omitted(self):
        payload = CrossApprovalExclusionSerializerTest().valid_payload()
        payload.pop("priority")
        serializer = CrossApprovalExclusionSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_duplicate_vulnerability_ids_in_one_request(self):
        payload = CrossApprovalExclusionSerializerTest().valid_payload()
        serializer = CrossApprovalRequestSerializer(data={"exclusions": [payload, payload]})

        self.assertFalse(serializer.is_valid())
        self.assertIn("exclusions", serializer.errors)


class CrossApprovalRequestValidationViewTest(SimpleTestCase):
    def test_reports_conflicting_request_id_and_status(self):
        request = Request(APIRequestFactory().get(
            "/api/v2/crossapproval_requests/validate-vulnerability-id/",
            {"vulnerability_id": "VULN-1"},
        ))
        exclusion = SimpleNamespace(
            request_id=9,
            request=SimpleNamespace(status="rejected"),
        )
        with patch(
            "dojo.api_v2.cross_approval.views.CrossApprovalExclusion.objects.filter"
        ) as exclusions_filter:
            exclusions_filter.return_value.select_related.return_value = [exclusion]
            response = CrossApprovalRequestViewSet().validate_vulnerability_id(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["conflicts"], [{"request_id": 9, "status": "rejected"}])