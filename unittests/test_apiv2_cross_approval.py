from contextlib import nullcontext
from unittest.mock import MagicMock, Mock, patch
from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from dojo.api_v2.cross_approval.permissions import IsCrossApprovalReviewer, IsCrossApprovalSubmitter
from dojo.api_v2.cross_approval.helpers import (
    _get_findings,
    check_new_findings_to_cross_approval_exclusion_list,
)
from dojo.api_v2.cross_approval.serializers import (
    CrossApprovalExclusionSerializer,
    CrossApprovalRequestSerializer,
)
from dojo.api_v2.cross_approval.views import CrossApprovalRequestViewSet
from dojo.engine_tools.cross_approval_views import crossapproval_list


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

    def test_accepts_exclusion_payload(self):
        serializer = CrossApprovalExclusionSerializer(data=self.valid_payload())

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["vulnerability_id"], "#sym:vulnerability_id")
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


class CrossApprovalHelpersTest(SimpleTestCase):
    def test_get_findings_matches_priority_or_severity_and_images(self):
        matching_finding = SimpleNamespace(
            priority_classification="High",
            severity="Low",
        )
        non_matching_finding = SimpleNamespace(
            priority_classification="Medium Low",
            severity="Info",
        )
        findings = MagicMock()
        findings.prefetch_related.return_value = findings
        findings.filter.return_value = findings
        findings.__iter__ = Mock(return_value=iter([matching_finding, non_matching_finding]))
        exclusion = SimpleNamespace(
            vulnerability_id="VULN-1",
            priority="high",
            severity="critical",
            image_names=["registry.example.com/base:1.0"],
        )

        with patch("dojo.api_v2.cross_approval.helpers.Finding.objects.filter", return_value=findings):
            result = _get_findings(exclusion)

        self.assertEqual(result, [matching_finding])
        findings.filter.assert_called_once()

    def test_check_new_findings_queues_current_approved_exclusions(self):
        exclusions = [SimpleNamespace(pk=3), SimpleNamespace(pk=5)]

        with (
            patch(
                "dojo.api_v2.cross_approval.helpers.CrossApprovalExclusion.objects.filter",
                return_value=exclusions,
            ),
            patch("dojo.api_v2.cross_approval.helpers.apply_cross_approval_exclusion.delay") as delay,
        ):
            check_new_findings_to_cross_approval_exclusion_list()

        delay.assert_any_call(3)
        delay.assert_any_call(5)
        self.assertEqual(delay.call_count, 2)


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


class CrossApprovalPermissionTest(SimpleTestCase):
    def _user(self):
        return SimpleNamespace(
            is_superuser=False,
            groups=SimpleNamespace(filter=Mock(return_value=SimpleNamespace(exists=Mock(return_value=False)))),
        )

    def test_submitter_permission_uses_configured_cross_approval_groups(self):
        user = self._user()
        with (
            patch(
                "dojo.api_v2.cross_approval.permissions.GeneralSettings.get_value",
                return_value=["cross-approval-group"],
            ),
            patch(
                "dojo.api_v2.cross_approval.permissions._is_in_group",
                return_value=True,
            ) as is_in_group,
        ):
            result = IsCrossApprovalSubmitter().has_permission(SimpleNamespace(user=user), None)

        self.assertTrue(result)
        is_in_group.assert_called_once_with(user, "cross-approval-group")

    def test_reviewer_permission_is_separate_from_submitter_permission(self):
        user = self._user()
        request = SimpleNamespace(user=user)

        with patch(
            "dojo.api_v2.cross_approval.permissions._is_in_group",
            side_effect=lambda current_user, group: group == "reviewers",
        ):
            with patch("dojo.api_v2.cross_approval.permissions.settings.REVIEWER_GROUP_NAME", "reviewers"):
                with patch("dojo.api_v2.cross_approval.permissions.settings.APPROVER_GROUP_NAME", "approvers"):
                    result = IsCrossApprovalReviewer().has_permission(request, None)

        self.assertTrue(result)
 
    def test_cross_approval_html_endpoint_allows_authenticated_readers(self):
        request = APIRequestFactory().get("/cross-approval/")
        request.session = {}
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            groups=SimpleNamespace(filter=Mock(return_value=SimpleNamespace(exists=Mock(return_value=False)))),
        )

        with (
            patch("dojo.engine_tools.cross_approval_views.render") as render,
            patch("dojo.engine_tools.cross_approval_views.is_cross_approval_submitter", return_value=False),
            patch("dojo.engine_tools.cross_approval_views.is_cross_approval_reviewer", return_value=False),
        ):
            crossapproval_list(request)

        render.assert_called_once()


class CrossApprovalRequestWorkflowViewTest(SimpleTestCase):
    def _view_for(self, instance):
        view = CrossApprovalRequestViewSet()
        view.get_object = Mock(return_value=instance)
        view.get_serializer = Mock(return_value=SimpleNamespace(data={"id": 7}))
        return view

    def test_approve_records_status_and_queues_exclusions(self):
        instance = SimpleNamespace(pk=7, status="pending", save=Mock())
        view = self._view_for(instance)
        request = SimpleNamespace(user=SimpleNamespace(username="maintainer"))

        with (
            patch("dojo.api_v2.cross_approval.views.log_status_change") as log_change,
            patch("dojo.api_v2.cross_approval.views.apply_request_exclusions") as apply_exclusions,
            patch("dojo.api_v2.cross_approval.views.notify_request_status") as notify,
        ):
            response = view._set_status(request, "approved")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(instance.status, "approved")
        log_change.assert_called_once_with(instance, request.user, "pending", "approved")
        apply_exclusions.assert_called_once_with(instance)
        notify.assert_called_once()

    def test_destroy_reverts_approved_exclusions_before_deletion(self):
        exclusion = SimpleNamespace(pk=3)
        instance = SimpleNamespace(
            status="approved",
            exclusions=SimpleNamespace(all=Mock(return_value=[exclusion])),
            delete=Mock(),
        )
        view = CrossApprovalRequestViewSet()

        with (
            patch("dojo.api_v2.cross_approval.views.transaction.atomic", return_value=nullcontext()),
            patch("dojo.api_v2.cross_approval.views.revert_cross_approval_exclusion") as revert,
        ):
            view.perform_destroy(instance)

        revert.assert_called_once_with(exclusion)
        instance.delete.assert_called_once_with()

    def test_expire_exclusion_serializes_a_refreshed_request(self):
        exclusion = SimpleNamespace(pk=3)
        instance = SimpleNamespace(
            status="approved",
            exclusions=SimpleNamespace(
                filter=Mock(return_value=SimpleNamespace(first=Mock(return_value=exclusion))),
            ),
        )
        refreshed_instance = SimpleNamespace(status="approved")
        view = self._view_for(instance)
        view.get_object.side_effect = [instance, refreshed_instance]
        request = SimpleNamespace(data={"exclusion_id": 3}, user=SimpleNamespace())

        with patch("dojo.api_v2.cross_approval.views.expire_cross_approval_exclusion"):
            response = view.expire_exclusion(request)

        self.assertEqual(response.status_code, 200)
        view.get_serializer.assert_called_once_with(refreshed_instance)

    def test_reopen_exclusion_serializes_a_refreshed_request(self):
        exclusion = SimpleNamespace(pk=3)
        instance = SimpleNamespace(
            status="approved",
            exclusions=SimpleNamespace(
                filter=Mock(return_value=SimpleNamespace(first=Mock(return_value=exclusion))),
            ),
        )
        refreshed_instance = SimpleNamespace(status="approved")
        view = self._view_for(instance)
        view.get_object.side_effect = [instance, refreshed_instance]
        request = SimpleNamespace(data={"exclusion_id": 3}, user=SimpleNamespace())

        with patch(
            "dojo.api_v2.cross_approval.views.reopen_cross_approval_exclusion",
            return_value=True,
        ):
            response = view.reopen_exclusion(request)

        self.assertEqual(response.status_code, 200)
        view.get_serializer.assert_called_once_with(refreshed_instance)