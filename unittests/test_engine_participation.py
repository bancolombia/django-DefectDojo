"""
Tests for HC (Hacking Continuo) Participation module.
"""
import datetime
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock

from dojo.models import (
    Product,
    GeneralSettings,
    Dojo_User,
)
from dojo.engine_participation.models import (
    HCParticipation,
    HCParticipationDiscussion,
    HCParticipationLog,
)
from dojo.engine_participation.filters import HCParticipationFilter
from dojo.engine_participation.forms import HCManualPostulationForm
from dojo.engine_participation.helpers import (
    run_hc_participation_evaluation,
    get_latest_hc_evaluation_for_product,
    get_manual_hc_postulation_eligibility_error,
    create_manual_hc_postulation,
    delete_hc_participation_records_by_date_range,
    return_hc_participation_to_pending,
    InvalidHCParticipationTransition,
    approve_hc_participation,
    mark_hc_participation_reviewed,
    reject_hc_participation,
    set_hc_request_preselection,
    _clear_general_setting_cache,
)


def _set_available_approvals_for_test(value: int) -> None:
    """Set available approvals in DB and purge Redis cache to avoid stale values between tests."""
    GeneralSettings.objects.update_or_create(
        name_key="HACKING_CONTINUOUS_APPROVAL_BAG_SIZE",
        defaults={"value": str(value), "data_type": "INT", "status": True},
    )
    _clear_general_setting_cache("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE")


def _set_confirm_ingress_criteria_for_test(criteria: list[str]) -> None:
    """Set ingress confirmation criteria in DB and purge Redis cache for deterministic tests."""
    GeneralSettings.objects.update_or_create(
        name_key="HC_CONFIRM_INGRESS_POSTULATION_CRITERIA",
        defaults={
            "value": ",".join(criteria),
            "data_type": "LIST",
            "status": True,
        },
    )
    _clear_general_setting_cache("HC_CONFIRM_INGRESS_POSTULATION_CRITERIA")


def _set_manual_postulation_criteria_for_test(criteria: list[str]) -> None:
    """Set manual postulation criteria in DB and purge Redis cache for deterministic tests."""
    GeneralSettings.objects.update_or_create(
        name_key="HC_MANUAL_POSTULATION_CRITERIA",
        defaults={
            "value": ",".join(criteria),
            "data_type": "LIST",
            "status": True,
        },
    )
    _clear_general_setting_cache("HC_MANUAL_POSTULATION_CRITERIA")


class HCParticipationModelTest(TestCase):
    """Tests for the HCParticipation model"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.product = Product.objects.first()
        self.user = Dojo_User.objects.get(username="admin")
    
    def test_model_creation(self):
        """Test that HC participation records can be created"""
        hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            business_criticality="high",
            was_in_hacking_continuous=False,
            reason="R3: Producto elegible",
            status="Pending",
            created_by=self.user,
        )
        
        self.assertIsNotNone(hc.uuid)
        self.assertIsNotNone(hc.create_date)
        self.assertEqual(hc.status, "Pending")
        self.assertEqual(hc.recommendation, "postulated")
    
    def test_model_str_representation(self):
        """Test string representation of the model"""
        hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
        )
        
        self.assertIn(self.product.name, str(hc))
        self.assertIn("postulated", str(hc))


class HCParticipationDiscussionTest(TestCase):
    """Tests for HCParticipationDiscussion model"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.product = Product.objects.first()
        self.user = Dojo_User.objects.get(username="admin")
        self.hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
        )
    
    def test_add_discussion(self):
        """Test adding a discussion to HC participation"""
        discussion = HCParticipationDiscussion.objects.create(
            hc_participation=self.hc,
            author=self.user,
            content="This is a test comment"
        )
        
        self.assertEqual(discussion.hc_participation, self.hc)
        self.assertEqual(discussion.author, self.user)
        self.assertIn("test comment", discussion.content)


class RunHCEvaluationTest(TestCase):
    """Tests for the run_hc_participation_evaluation function"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.user = Dojo_User.objects.get(username="admin")
        Token.objects.get_or_create(user=self.user)
        self.product = Product.objects.first()
        self.product.business_criticality = "high"
        self.product.description = "Service Metadata"
        self.product.save()
    
    @override_settings(
        HC_PARTICIPATION_POSTULATED_ENDPOINT="http://hc-microservice.local/postulated",
        HC_PARTICIPATION_POSTULATED_TAGS=["fluidattacks", "fluid_hacker", "devsecops_hacker"],
        HC_PARTICIPATION_DAYS=30,
        HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"],
        HC_PARTICIPATION_POSTULATED_BUSINESS_CRITICALITY=[],
    )
    @patch('dojo.engine_participation.helpers.requests.post')
    def test_run_evaluation_creates_records(self, mock_post):
        """Test that evaluation creates database records"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "product": self.product.name,
                "id_product": str(self.product.id),
                "product_type": "EVC - APIS",
                "business_criticality": "high",
                "class_id": "BMC_APPLICATION",
            }
        ]
        mock_post.return_value = mock_response
        
        initial_count = HCParticipation.objects.count()
        
        result = run_hc_participation_evaluation(user=self.user)
        
        self.assertGreaterEqual(
            HCParticipation.objects.count(),
            initial_count
        )
        self.assertIsNotNone(result["batch_id"])
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(
            kwargs["json"],
            {
                "tags": ["fluidattacks", "fluid_hacker", "devsecops_hacker"],
                "days": 30,
                "classID": ["BMC_APPLICATION"],
                "businessCriticality": [],
            },
        )
    
    @override_settings(HC_PARTICIPATION_POSTULATED_ENDPOINT="http://hc-microservice.local/postulated")
    @patch('dojo.engine_participation.helpers.requests.post')
    def test_run_evaluation_returns_summary(self, mock_post):
        """Test that evaluation returns proper summary"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "product": self.product.name,
                "id_product": str(self.product.id),
                "product_type": "EVC - APIS",
                "business_criticality": "high",
                "class_id": "BMC_APPLICATION",
            }
        ]
        mock_post.return_value = mock_response
        
        result = run_hc_participation_evaluation(user=self.user)
        
        self.assertIn("summary", result)
        self.assertIn("postulated", result["summary"])
        self.assertIn("already_in_hc", result["summary"])
        self.assertIn("not_eligible", result["summary"])
        self.assertIn("scope", result)
        self.assertIn("rows_from_microservice", result["scope"])

    @override_settings(HC_PARTICIPATION_POSTULATED_ENDPOINT="http://hc-microservice.local/postulated")
    @patch('dojo.engine_participation.helpers.requests.post')
    def test_run_evaluation_skips_existing_active_request(self, mock_post):
        """Test that evaluation does not duplicate active HC requests"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "product": self.product.name,
                "id_product": str(self.product.id),
                "product_type": "EVC - APIS",
                "business_criticality": "high",
                "class_id": "BMC_APPLICATION",
            }
        ]
        mock_post.return_value = mock_response

        HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        result = run_hc_participation_evaluation(user=self.user)

        self.assertEqual(
            HCParticipation.objects.filter(product=self.product, status="Pending").count(),
            1,
        )
        self.assertEqual(result["requests_created"], 0)
    
    @override_settings(HC_PARTICIPATION_POSTULATED_ENDPOINT="http://hc-microservice.local/postulated")
    @patch('dojo.engine_participation.helpers.requests.post')
    def test_run_evaluation_empty_products(self, mock_post):
        """Test evaluation with empty microservice response"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        mock_post.return_value = mock_response
        
        result = run_hc_participation_evaluation(user=self.user)
        
        self.assertEqual(result["total_evaluated"], 0)
        self.assertEqual(result["scope"]["rows_from_microservice"], 0)

    @override_settings(
        HC_PARTICIPATION_POSTULATED_ENDPOINT="http://hc-microservice.local/postulated",
        OPERATIVE_USER="operative",
    )
    @patch('dojo.engine_participation.helpers.requests.post')
    def test_run_evaluation_without_user_uses_operative_user_token(self, mock_post):
        """Evaluation without explicit user resolves DD_OPERATIVE_USER."""
        operative_user = Dojo_User.objects.create_user(
            username="operative",
            email="operative@test.com",
            password="testpass123",
        )
        operative_token, _created = Token.objects.get_or_create(user=operative_user)

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        mock_post.return_value = mock_response

        result = run_hc_participation_evaluation(user=None)

        self.assertEqual(result["total_evaluated"], 0)
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            f"Token {operative_token.key}",
        )

    @override_settings(
        HC_PARTICIPATION_POSTULATED_ENDPOINT="http://hc-microservice.local/postulated",
        HC_PARTICIPATION_ALREADY_IN_HC_ENDPOINT="http://hc-microservice.local/already",
        HC_PARTICIPATION_POSTULATED_TAGS=["fluidattacks", "fluid_hacker", "devsecops_hacker"],
        HC_PARTICIPATION_DAYS=300,
        HC_PARTICIPATION_POSTULATED_CLASSID=[],
        HC_PARTICIPATION_POSTULATED_BUSINESS_CRITICALITY=[],
    )
    @patch('dojo.engine_participation.helpers.requests.post')
    def test_run_evaluation_fetches_already_in_hc_and_creates_requests(self, mock_post):
        """Evaluation calls both endpoints and creates review requests for already_in_hc."""
        postulated_response = MagicMock()
        postulated_response.raise_for_status.return_value = None
        postulated_response.json.return_value = [
            {
                "product": self.product.name,
                "id_product": str(self.product.id),
                "business_criticality": "high",
            }
        ]

        product_two = Product.objects.exclude(id=self.product.id).first()
        if not product_two:
            product_two = Product.objects.create(
                name="HC Product Two",
                description="HC second product",
                business_criticality="medium",
                prod_type=self.product.prod_type,
            )

        already_response = MagicMock()
        already_response.raise_for_status.return_value = None
        already_response.json.return_value = [
            {
                "product": product_two.name,
                "id_product": str(product_two.id),
                "business_criticality": "medium",
            }
        ]

        mock_post.side_effect = [postulated_response, already_response]

        result = run_hc_participation_evaluation(user=self.user)

        self.assertEqual(mock_post.call_count, 2)
        first_call = mock_post.call_args_list[0].kwargs
        second_call = mock_post.call_args_list[1].kwargs

        expected_body = {
            "tags": ["fluidattacks", "fluid_hacker", "devsecops_hacker"],
            "days": 300,
            "classID": [],
            "businessCriticality": [],
        }
        self.assertEqual(first_call["json"], expected_body)
        self.assertEqual(second_call["json"], expected_body)

        self.assertEqual(result["summary"]["postulated"], 1)
        self.assertEqual(result["summary"]["already_in_hc"], 1)
        self.assertEqual(result["requests_created"], 2)

        self.assertTrue(
            HCParticipation.objects.filter(
                product=product_two,
                recommendation="already_in_hc",
                status="Pending",
            ).exists()
        )


class ApproveRejectHCTest(TestCase):
    """Tests for approve and reject functions"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.product = Product.objects.first()
        self.user = Dojo_User.objects.get(username="admin")
        _set_available_approvals_for_test(2)
        self.hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Reviewed",
            created_by=self.user,
        )
    
    def test_approve_hc_participation(self):
        """Test approving HC participation"""
        approve_hc_participation(self.hc, self.user)
        
        self.hc.refresh_from_db()
        self.assertEqual(self.hc.status, "Approved")
        self.assertEqual(self.hc.final_status, "Approved")
        self.assertEqual(self.hc.approved_by, self.user)
        self.assertIsNotNone(self.hc.approved_at)
        
        log = HCParticipationLog.objects.filter(hc_participation=self.hc).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.current_status, "Approved")

        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 2)
    
    def test_reject_hc_participation(self):
        """Test rejecting HC participation"""
        reject_hc_participation(self.hc, self.user)
        
        self.hc.refresh_from_db()
        self.assertEqual(self.hc.status, "Rejected")
        self.assertEqual(self.hc.final_status, "Rejected")
        self.assertEqual(self.hc.rejected_by, self.user)
        
        log = HCParticipationLog.objects.filter(hc_participation=self.hc).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.current_status, "Rejected")

    def test_reject_preselected_clears_flag_and_restores_approval(self):
        """Rejecting a preselected request removes the flag and increments available approvals."""
        _set_available_approvals_for_test(3)
        self.hc.security_posture_data = {"is_preselected_for_hc": True}
        self.hc.save()

        reject_hc_participation(self.hc, self.user)

        self.hc.refresh_from_db()
        self.assertEqual(self.hc.status, "Rejected")
        self.assertFalse(self.hc.security_posture_data.get("is_preselected_for_hc", False))
        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 4)

    def test_reject_reviewed_postulation_restores_approval(self):
        """Rejecting a reviewed postulation should restore one available approval."""
        _set_available_approvals_for_test(2)

        reject_hc_participation(self.hc, self.user)

        self.hc.refresh_from_db()
        self.assertEqual(self.hc.status, "Rejected")
        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 3)

    def test_review_hc_participation_requires_pending_status(self):
        """Test reviewing only works from Pending status"""
        self.hc.status = "Approved"
        self.hc.final_status = "Approved"
        self.hc.save()

        with self.assertRaises(InvalidHCParticipationTransition):
            mark_hc_participation_reviewed(self.hc, self.user)

    def test_approve_hc_participation_requires_reviewed_status(self):
        """Test approving only works from Reviewed status"""
        self.hc.status = "Pending"
        self.hc.save()

        with self.assertRaises(InvalidHCParticipationTransition):
            approve_hc_participation(self.hc, self.user)

    def test_reject_hc_participation_rejects_terminal_status(self):
        """Test rejecting does not work from terminal statuses"""
        self.hc.status = "Approved"
        self.hc.final_status = "Approved"
        self.hc.save()

        with self.assertRaises(InvalidHCParticipationTransition):
            reject_hc_participation(self.hc, self.user)

    def test_approve_hc_participation_does_not_consume_available_approvals(self):
        """Approver action does not consume or validate available approvals"""
        _set_available_approvals_for_test(0)

        approve_hc_participation(self.hc, self.user)

        self.hc.refresh_from_db()
        self.assertEqual(self.hc.status, "Approved")

        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 0)

    def test_review_postulated_consumes_available_approval(self):
        """Reviewing a postulated request consumes one available approval"""
        pending_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        mark_hc_participation_reviewed(pending_postulation, self.user)

        pending_postulation.refresh_from_db()
        self.assertEqual(pending_postulation.status, "Reviewed")
        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 1)

    def test_review_postulated_fails_when_no_available_approvals(self):
        """Reviewer cannot mark postulated as reviewed when there are no available approvals"""
        _set_available_approvals_for_test(0)
        pending_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        with self.assertRaises(InvalidHCParticipationTransition):
            mark_hc_participation_reviewed(pending_postulation, self.user)

        pending_postulation.refresh_from_db()
        self.assertEqual(pending_postulation.status, "Pending")

    def test_review_postulated_preselected_does_not_consume_approval_twice(self):
        """If request was already pre-selected, review should not consume an extra approval"""
        pending_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        set_hc_request_preselection(pending_postulation, True)
        available_after_preselection = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_after_preselection), 1)

        mark_hc_participation_reviewed(pending_postulation, self.user)

        available_after_review = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_after_review), 1)

    def test_review_postulated_preselected_fails_when_approvals_negative(self):
        """When available approvals is negative, no postulated request can be reviewed (including pre-selected ones)."""
        pending_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        set_hc_request_preselection(pending_postulation, True)

        second_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )
        set_hc_request_preselection(second_postulation, True)

        third_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )
        set_hc_request_preselection(third_postulation, True)

        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertLess(int(available_approvals), 0)

        # Pre-selected products are still blocked when count is negative;
        # reviewer must remove some pre-selections first.
        with self.assertRaises(InvalidHCParticipationTransition):
            mark_hc_participation_reviewed(pending_postulation, self.user)

        pending_postulation.refresh_from_db()
        self.assertEqual(pending_postulation.status, "Pending")

    def test_preselect_and_remove_preselection_adjust_approvals(self):
        """Pre-select decreases available approvals and removing pre-selection increases them"""
        pending_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        set_hc_request_preselection(pending_postulation, True)
        available_after_preselection = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_after_preselection), 1)

        set_hc_request_preselection(pending_postulation, False)
        available_after_removal = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_after_removal), 2)

    def test_review_already_in_hc_increments_available_approvals(self):
        """Reviewing an already_in_hc removal request increases available approvals by 1"""
        _set_available_approvals_for_test(0)
        removal_request = HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Pending",
            was_in_hacking_continuous=True,
            created_by=self.user,
        )

        mark_hc_participation_reviewed(removal_request, self.user)

        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 1)

    def test_reject_reviewed_already_in_hc_reverts_available_approvals(self):
        """Rejecting a reviewed already_in_hc removal request must revert the approval added on review."""
        _set_available_approvals_for_test(0)
        removal_request = HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Pending",
            was_in_hacking_continuous=True,
            created_by=self.user,
        )

        mark_hc_participation_reviewed(removal_request, self.user)
        available_after_review = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_after_review), 1)

        reject_hc_participation(removal_request, self.user)

        removal_request.refresh_from_db()
        self.assertEqual(removal_request.status, "Rejected")
        available_after_reject = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_after_reject), 0)

    def test_return_to_pending_preserves_history_and_discussions(self):
        """Returning to Pending must keep prior logs/discussions and append a new log entry."""
        _set_available_approvals_for_test(2)
        HCParticipationLog.objects.create(
            hc_participation=self.hc,
            changed_by=self.user,
            previous_status="Pending",
            current_status="Reviewed",
            notes="Request marked as reviewed",
        )
        HCParticipationDiscussion.objects.create(
            hc_participation=self.hc,
            author=self.user,
            content="Keep this discussion",
        )

        return_hc_participation_to_pending(self.hc, self.user, reason="Sent back for reevaluation")

        self.hc.refresh_from_db()
        self.assertEqual(self.hc.status, "Pending")
        self.assertIsNone(self.hc.final_status)
        self.assertEqual(self.hc.discussions.count(), 1)
        self.assertEqual(self.hc.logs.count(), 2)

        last_log = self.hc.logs.order_by("-changed_at").first()
        self.assertEqual(last_log.previous_status, "Reviewed")
        self.assertEqual(last_log.current_status, "Pending")
        self.assertIn("Sent back for reevaluation", last_log.notes)

        available_approvals = GeneralSettings.get_value("HACKING_CONTINUOUS_APPROVAL_BAG_SIZE", 0)
        self.assertEqual(int(available_approvals), 3)


class GetLatestEvaluationTest(TestCase):
    """Tests for the get_latest_hc_evaluation_for_product function"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.product = Product.objects.first()
        self.user = Dojo_User.objects.get(username="admin")
    
    def test_no_evaluation_returns_none(self):
        """Test that None is returned when no evaluation exists"""
        HCParticipation.objects.filter(product=self.product).delete()
        
        result = get_latest_hc_evaluation_for_product(self.product.id)
        
        self.assertIsNone(result)
    
    def test_returns_latest_evaluation(self):
        """Test that the latest evaluation is returned"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="not_eligible",
            status="Pending",
        )
        
        latest = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Approved",
            final_status="Approved",
            approved_by=self.user,
        )
        
        result = get_latest_hc_evaluation_for_product(self.product.id)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["evaluation_id"], str(latest.uuid))
        self.assertEqual(result["recommendation"], "postulated")
        self.assertEqual(result["status"], "Approved")


class HCParticipationViewsTest(TestCase):
    """Tests for HC Participation views"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.client = APIClient()
        token = Token.objects.get(user__username="admin")
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        
        self.user = Dojo_User.objects.get(username="admin")
        self.product = Product.objects.first()
        
        self.hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )
        _set_available_approvals_for_test(3)
    
    def test_list_view(self):
        """Test HC participation list view"""
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        
        response = client.get(reverse('hc_participations'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_list_view_includes_hc_summary(self):
        """List view shows summary panel with available approvals and counters"""
        from django.test import Client

        HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Approved",
            created_by=self.user,
        )

        client = Client()
        client.force_login(self.user)
        response = client.get(reverse("hc_participations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SDT Participation Summary")
        self.assertContains(response, "Available approvals")
        self.assertContains(response, "Postulated products")
        self.assertContains(response, "Pre-selected products")
        self.assertContains(response, "Products in SDT")

    def test_list_view_shows_approvals_in_red_when_negative(self):
        """When available approvals is negative, summary value should be rendered in red"""
        _set_available_approvals_for_test(-1)

        from django.test import Client
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse("hc_participations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'style="color: #d11d38;"')
        self.assertContains(
            response,
            "Available approvals is negative. Remove pre-selections or review already_in_hc removals before reviewing more postulated requests.",
        )
    
    def test_show_view(self):
        """Test HC participation detail view"""
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        
        response = client.get(reverse('hc_participation', args=[str(self.hc.uuid)]))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_show_view_includes_security_posture_async_loader(self):
        """Detail view includes async loader for security posture data."""
        from django.test import Client

        self.hc.security_posture_data = {"product_risk_posture_url": "/product/risk_posture/product?product_id=1"}
        self.hc.save()

        client = Client()
        client.force_login(self.user)
        response = client.get(reverse("hc_participation", args=[str(self.hc.uuid)]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("product_risk_posture") + f"?product_id={self.product.id}")
        self.assertContains(response, "Open Risk Posture")
    
    def test_run_evaluation_requires_admin(self):
        """Test that run evaluation requires admin privileges"""
        from django.test import Client
        
        regular_user = Dojo_User.objects.create_user(
            username="regularuser",
            email="regular@test.com",
            password="testpass123"
        )
        
        client = Client()
        client.force_login(regular_user)
        
        response = client.post(reverse('run_hc_evaluation'))
        
        self.assertEqual(response.status_code, 403)

    def test_review_requires_post(self):
        """Test review action rejects GET requests"""
        from django.test import Client

        client = Client()
        client.force_login(self.user)

        response = client.get(reverse('review_hc_participation', args=[str(self.hc.uuid)]))

        self.assertEqual(response.status_code, 405)

    @patch("dojo.engine_participation.views.is_in_group", return_value=True)
    @patch("dojo.engine_participation.views.has_valid_comments", return_value=True)
    @patch("dojo.engine_participation.views.mark_hc_participation_reviewed")
    def test_review_requires_checklist_for_postulated_requests(
        self,
        mock_mark_reviewed,
        _mock_has_comments,
        _mock_is_in_group,
    ):
        """Reviewing postulated requests requires full checklist when configured."""
        from django.test import Client
        _set_confirm_ingress_criteria_for_test(["Criterion A", "Criterion B"])

        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("review_hc_participation", args=[str(self.hc.uuid)]),
            data={},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must confirm all ingress checklist criteria to mark as reviewed.")
        mock_mark_reviewed.assert_not_called()

    @patch("dojo.engine_participation.views.is_in_group", return_value=True)
    @patch("dojo.engine_participation.views.has_valid_comments", return_value=True)
    @patch("dojo.engine_participation.views.mark_hc_participation_reviewed")
    def test_review_rejects_partial_checklist_for_postulated_requests(
        self,
        mock_mark_reviewed,
        _mock_has_comments,
        _mock_is_in_group,
    ):
        """Reviewing postulated requests with partial checklist must be rejected."""
        from django.test import Client
        _set_confirm_ingress_criteria_for_test(["Criterion A", "Criterion B"])

        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("review_hc_participation", args=[str(self.hc.uuid)]),
            data={"criteria": ["Criterion A"]},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must confirm all ingress checklist criteria to mark as reviewed.")
        mock_mark_reviewed.assert_not_called()

    @patch("dojo.engine_participation.views.is_in_group", return_value=True)
    @patch("dojo.engine_participation.views.has_valid_comments", return_value=True)
    @patch("dojo.engine_participation.views.get_hc_approvers_members", return_value=[])
    @patch("dojo.engine_participation.views.create_notification")
    @patch("dojo.engine_participation.views.mark_hc_participation_reviewed")
    def test_review_accepts_checklist_for_postulated_requests(
        self,
        mock_mark_reviewed,
        _mock_create_notification,
        _mock_approvers,
        _mock_has_comments,
        _mock_is_in_group,
    ):
        """Review action forwards checklist criteria when all configured are selected."""
        from django.test import Client
        _set_confirm_ingress_criteria_for_test(["Criterion A", "Criterion B"])

        mock_mark_reviewed.return_value = self.hc

        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("review_hc_participation", args=[str(self.hc.uuid)]),
            data={"criteria": ["Criterion A", "Criterion B"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("hc_participation", args=[str(self.hc.uuid)]))
        mock_mark_reviewed.assert_called_once()
        _, kwargs = mock_mark_reviewed.call_args
        self.assertEqual(kwargs.get("confirmation_criteria"), ["Criterion A", "Criterion B"])

    def test_approve_requires_post(self):
        """Test approve action rejects GET requests"""
        from django.test import Client

        client = Client()
        client.force_login(self.user)

        response = client.get(reverse('approve_hc_participation', args=[str(self.hc.uuid)]))

        self.assertEqual(response.status_code, 405)

    def test_reject_requires_post(self):
        """Test reject action rejects GET requests"""
        from django.test import Client

        client = Client()
        client.force_login(self.user)

        response = client.get(reverse('reject_hc_participation', args=[str(self.hc.uuid)]))

        self.assertEqual(response.status_code, 405)

    def test_run_evaluation_requires_post(self):
        """Test run evaluation action rejects GET requests"""
        from django.test import Client

        client = Client()
        client.force_login(self.user)

        response = client.get(reverse('run_hc_evaluation'))

        self.assertEqual(response.status_code, 405)

    def test_api_run_evaluation_requires_authentication(self):
        """Test API endpoint requires token authentication"""
        api_client = APIClient()

        response = api_client.post(reverse("api_hc_run_evaluation"), format="json")

        self.assertEqual(response.status_code, 403)

    @patch("dojo.api_v2.engine_participation.views.run_hc_participation_evaluation")
    def test_api_run_evaluation_with_admin_token(self, mock_run_evaluation):
        """Test API endpoint executes evaluation with admin token"""
        mock_run_evaluation.return_value = {
            "batch_id": "batch-1",
            "total_evaluated": 1,
            "scope": {
                "total_products": 1,
                "classid_candidates": 1,
                "skipped_by_classid": 0,
            },
            "summary": {
                "postulated": 1,
                "already_in_hc": 0,
                "not_eligible": 0,
                "errors": 0,
            },
            "requests_created": 1,
            "results": [],
        }

        response = self.client.post(reverse("api_hc_run_evaluation"), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["data"]["batch_id"], "batch-1")

    def test_api_run_evaluation_forbids_non_staff_user(self):
        """Test API endpoint denies non-staff users even with token"""
        regular_user = Dojo_User.objects.create_user(
            username="regular_api_user",
            email="regular_api@test.com",
            password="testpass123",
            is_staff=False,
        )
        regular_token = Token.objects.create(user=regular_user)

        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Token " + regular_token.key)

        response = api_client.post(reverse("api_hc_run_evaluation"), format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["status"], "forbidden")

    @patch("dojo.engine_participation.views.is_in_group", return_value=True)
    def test_preselect_redirects_to_next_path(self, _mock_is_in_group):
        """Preselect action should redirect back to the provided next path."""
        from django.test import Client

        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("preselect_hc_participation", args=[str(self.hc.uuid)]),
            data={"next": "/engine_participation/hc_participations?status=Pending&postulated_page=2"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "/engine_participation/hc_participations?status=Pending&postulated_page=2",
        )

    @patch("dojo.engine_participation.views.is_in_group", return_value=True)
    def test_remove_preselection_rejects_external_next(self, _mock_is_in_group):
        """External next URLs are rejected; fallback goes to hc_participations."""
        from django.test import Client

        self.hc.security_posture_data = {"is_preselected_for_hc": True}
        self.hc.save()

        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse("remove_hc_preselection", args=[str(self.hc.uuid)]),
            data={"next": "https://evil.example/path"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("hc_participations"))


class HCManualPostulationFormTest(TestCase):
    """Tests for HCManualPostulationForm"""

    def test_choices_loaded_from_settings(self):
        """Form choices must come from GeneralSettings HC_MANUAL_POSTULATION_CRITERIA"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        form = HCManualPostulationForm()

        self.assertEqual(
            list(form.fields["criteria"].choices),
            [("Criterion A", "Criterion A"), ("Criterion B", "Criterion B")],
        )

    def test_requires_at_least_one_criterion(self):
        """Submitting the form without any criteria selected must be invalid"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        form = HCManualPostulationForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn("criteria", form.errors)

    def test_valid_with_one_criterion_selected(self):
        """Selecting a single criterion must be enough to make the form valid"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        form = HCManualPostulationForm(data={"criteria": ["Criterion A"]})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["criteria"], ["Criterion A"])

    def test_valid_with_multiple_criteria_selected(self):
        """Selecting multiple criteria must be preserved in cleaned_data"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        form = HCManualPostulationForm(data={"criteria": ["Criterion A", "Criterion B"]})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["criteria"], ["Criterion A", "Criterion B"])

    def test_invalid_choice_not_in_settings_is_rejected(self):
        """A criterion that is not part of the configured choices must be rejected"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        form = HCManualPostulationForm(data={"criteria": ["Not a configured criterion"]})

        self.assertFalse(form.is_valid())
        self.assertIn("criteria", form.errors)


class HCConfirmIngressPostulationFormTest(TestCase):
    """Tests for HCConfirmIngressPostulationForm behavior"""

    def test_requires_at_least_one_criterion_when_configured(self):
        from dojo.engine_participation.forms import HCConfirmIngressPostulationForm
        _set_confirm_ingress_criteria_for_test(["Criterion A", "Criterion B"])

        form = HCConfirmIngressPostulationForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn("criteria", form.errors)

    def test_allows_empty_selection_when_not_configured(self):
        from dojo.engine_participation.forms import HCConfirmIngressPostulationForm
        _set_confirm_ingress_criteria_for_test([])

        form = HCConfirmIngressPostulationForm(data={})

        self.assertTrue(form.is_valid())


class ManualHCPostulationEligibilityTest(TestCase):
    """Tests for get_manual_hc_postulation_eligibility_error"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product = Product.objects.first()
        self.product.description = "classid: BMC_APPLICATION"
        self.product.save()
        self.user = Dojo_User.objects.get(username="admin")
        HCParticipation.objects.filter(product=self.product).delete()

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_eligible_product_returns_none(self):
        """A product with no active requests and an allowed class_id is eligible"""
        error = get_manual_hc_postulation_eligibility_error(self.product)

        self.assertIsNone(error)

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["OTHER_CLASSID"])
    def test_disallowed_classid_returns_error(self):
        """A product whose class_id is not in the allowed list is not eligible"""
        error = get_manual_hc_postulation_eligibility_error(self.product)

        self.assertIsNotNone(error)
        self.assertIn("class_id is not allowed", error)

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_pending_postulation_returns_error(self):
        """A product with an existing pending postulation is not eligible"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated_manually",
            status="Pending",
            created_by=self.user,
        )

        error = get_manual_hc_postulation_eligibility_error(self.product)

        self.assertEqual(error, "A pending HC postulation already exists for this product.")

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_already_in_hc_returns_error(self):
        """A product already in SDT is not eligible"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Reviewed",
            created_by=self.user,
        )

        error = get_manual_hc_postulation_eligibility_error(self.product)

        self.assertEqual(error, "This product is already in SDT.")

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_already_in_hc_with_pending_status_is_not_confused_with_pending_postulation(self):
        """Regression test: an 'already_in_hc' record with status Pending must
        be reported as 'already in SDT', not as a pending postulation."""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Pending",
            created_by=self.user,
        )

        error = get_manual_hc_postulation_eligibility_error(self.product)

        self.assertEqual(error, "This product is already in SDT.")


class CreateManualHCPostulationTest(TestCase):
    """Tests for create_manual_hc_postulation"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product = Product.objects.first()
        self.product.description = "classid: BMC_APPLICATION"
        self.product.business_criticality = "high"
        self.product.save()
        self.user = Dojo_User.objects.get(username="admin")
        HCParticipation.objects.filter(product=self.product).delete()

    def test_requires_at_least_one_criterion(self):
        """No criteria provided must fail without hitting the database"""
        hc_request, error = create_manual_hc_postulation(self.product, self.user, criteria=[])

        self.assertIsNone(hc_request)
        self.assertEqual(
            error,
            "You must select at least one criterion to submit the manual postulation.",
        )
        self.assertFalse(HCParticipation.objects.filter(product=self.product).exists())

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_creates_request_with_selected_criteria(self):
        """A valid eligible product with criteria must create a Pending request
        storing the criteria in security_posture_data and in the reason text"""
        criteria = ["Criterion A", "Criterion B"]

        hc_request, error = create_manual_hc_postulation(self.product, self.user, criteria=criteria)

        self.assertIsNone(error)
        self.assertIsNotNone(hc_request)
        hc_request.refresh_from_db()
        self.assertEqual(hc_request.recommendation, "postulated_manually")
        self.assertEqual(hc_request.status, "Pending")
        self.assertEqual(hc_request.created_by, self.user)
        self.assertEqual(
            hc_request.security_posture_data.get("manual_postulation_criteria"),
            criteria,
        )
        self.assertIn("Criterion A", hc_request.reason)
        self.assertIn("Criterion B", hc_request.reason)

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["OTHER_CLASSID"])
    def test_does_not_create_request_when_classid_not_allowed(self):
        """The product class_id validation must block creation of the request"""
        hc_request, error = create_manual_hc_postulation(
            self.product, self.user, criteria=["Criterion A"],
        )

        self.assertIsNone(hc_request)
        self.assertIn("class_id is not allowed", error)
        self.assertFalse(HCParticipation.objects.filter(product=self.product).exists())

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_does_not_create_request_when_pending_postulation_exists(self):
        """An existing pending postulation must block creation of a new one"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )

        hc_request, error = create_manual_hc_postulation(
            self.product, self.user, criteria=["Criterion A"],
        )

        self.assertIsNone(hc_request)
        self.assertEqual(error, "A pending HC postulation already exists for this product.")
        self.assertEqual(HCParticipation.objects.filter(product=self.product).count(), 1)

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_does_not_create_request_when_already_in_hc(self):
        """A product already in SDT must block creation of a new request"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Reviewed",
            created_by=self.user,
        )

        hc_request, error = create_manual_hc_postulation(
            self.product, self.user, criteria=["Criterion A"],
        )

        self.assertIsNone(hc_request)
        self.assertEqual(error, "This product is already in SDT.")
        self.assertEqual(HCParticipation.objects.filter(product=self.product).count(), 1)


class ManualHCPostulationViewTest(TestCase):
    """Tests for the manual HC postulation view (GET criteria form / POST creation)"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product = Product.objects.first()
        self.product.description = "classid: BMC_APPLICATION"
        self.product.save()
        HCParticipation.objects.filter(product=self.product).delete()

        self.admin = Dojo_User.objects.get(username="admin")
        self.client = Client()
        self.client.force_login(self.admin)

        self.url = reverse("create_manual_hc_postulation", args=[self.product.id])

    def test_permission_denied_for_regular_user(self):
        """A user without staff/superuser/reviewer/approver privileges cannot access the view"""
        regular_user = Dojo_User.objects.create_user(
            username="hc_regular_user",
            email="hc_regular_user@test.com",
            password="testpass123",
        )
        client = Client()
        client.force_login(regular_user)

        response = client.get(self.url)

        self.assertEqual(response.status_code, 403)

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_get_renders_criteria_form_when_eligible(self):
        """GET must render the criteria form when the product is eligible"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manual HC Postulation")
        self.assertContains(response, "Submit Manual Postulation")

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["OTHER_CLASSID"])
    def test_get_redirects_when_classid_not_allowed(self):
        """GET must redirect without showing the form when class_id is not allowed"""
        response = self.client.get(self.url, follow=True)

        self.assertRedirects(response, reverse("view_product", args=[self.product.id]))
        page_messages = list(response.context["messages"])
        self.assertTrue(any("class_id is not allowed" in str(m) for m in page_messages))

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_get_redirects_when_pending_postulation_exists(self):
        """GET must redirect without showing the form when a pending postulation exists"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.admin,
        )

        response = self.client.get(self.url, follow=True)

        self.assertRedirects(response, reverse("view_product", args=[self.product.id]))
        page_messages = list(response.context["messages"])
        self.assertTrue(any("pending HC postulation already exists" in str(m) for m in page_messages))

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_get_redirects_when_already_in_hc(self):
        """GET must redirect without showing the form when the product is already in HC"""
        HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Pending",
            created_by=self.admin,
        )

        response = self.client.get(self.url, follow=True)

        self.assertRedirects(response, reverse("view_product", args=[self.product.id]))
        page_messages = list(response.context["messages"])
        self.assertTrue(any("already in SDT" in str(m) for m in page_messages))

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_post_without_criteria_shows_validation_error(self):
        """POST without any criteria selected must re-render the form with an error"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        response = self.client.post(self.url, data={})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must select at least one criterion")
        self.assertFalse(HCParticipation.objects.filter(product=self.product).exists())

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_post_with_criteria_creates_postulation_and_redirects(self):
        """POST with at least one criterion must create the request and redirect"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        response = self.client.post(
            self.url,
            data={"criteria": ["Criterion A"]},
            follow=True,
        )

        self.assertRedirects(response, reverse("view_product", args=[self.product.id]))
        hc_request = HCParticipation.objects.get(product=self.product)
        self.assertEqual(hc_request.recommendation, "postulated_manually")
        self.assertEqual(
            hc_request.security_posture_data.get("manual_postulation_criteria"),
            ["Criterion A"],
        )
        page_messages = list(response.context["messages"])
        self.assertTrue(any("Manual HC postulation created successfully" in str(m) for m in page_messages))

    @override_settings(HC_PARTICIPATION_POSTULATED_CLASSID=["BMC_APPLICATION"])
    def test_post_when_product_becomes_ineligible_between_get_and_post(self):
        """POST must be re-validated even if it passed the initial GET check
        (race-condition safety net implemented in create_manual_hc_postulation)"""
        _set_manual_postulation_criteria_for_test(["Criterion A", "Criterion B"])
        HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.admin,
        )

        response = self.client.post(
            self.url,
            data={"criteria": ["Criterion A"]},
            follow=True,
        )

        self.assertRedirects(response, reverse("view_product", args=[self.product.id]))
        self.assertEqual(HCParticipation.objects.filter(product=self.product).count(), 1)
        page_messages = list(response.context["messages"])
        self.assertTrue(any("pending HC postulation already exists" in str(m) for m in page_messages))


class HCParticipationFilterTest(TestCase):
    """Tests for HCParticipationFilter"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product = Product.objects.first()
        HCParticipation.objects.filter(product=self.product).delete()

    def test_filters_by_product_type_name_icontains(self):
        """product_type filter must match by product type name (case-insensitive
        partial match), not by id"""
        hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
        )
        product_type_name = self.product.prod_type.name

        filtered = HCParticipationFilter(
            {"product_type": product_type_name.lower()},
            queryset=HCParticipation.objects.filter(product=self.product),
        )

        self.assertIn(hc, filtered.qs)

    def test_status_filter_removal_approved(self):
        """'Removal Approved' must match already_in_hc requests approved for removal"""
        removal_candidate = HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Approved",
        )

        filtered = HCParticipationFilter(
            {"status": "Removal Approved"},
            queryset=HCParticipation.objects.filter(product=self.product),
        )

        self.assertIn(removal_candidate, filtered.qs)

    def test_status_filter_continues_in_hc(self):
        """'Continues in HC' must match already_in_hc requests rejected for removal"""
        continues_in_hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Rejected",
        )

        filtered = HCParticipationFilter(
            {"status": "Continues in HC"},
            queryset=HCParticipation.objects.filter(product=self.product),
        )

        self.assertIn(continues_in_hc, filtered.qs)

    def test_status_filter_approved_excludes_already_in_hc(self):
        """'Approved' must only match real postulations, not already_in_hc removals"""
        approved_postulation = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Approved",
        )
        removal_candidate = HCParticipation.objects.create(
            product=self.product,
            recommendation="already_in_hc",
            status="Approved",
        )

        filtered = HCParticipationFilter(
            {"status": "Approved"},
            queryset=HCParticipation.objects.filter(product=self.product),
        )

        self.assertIn(approved_postulation, filtered.qs)
        self.assertNotIn(removal_candidate, filtered.qs)


class DeleteHCParticipationRecordsHelperTest(TestCase):
    """Tests for delete_hc_participation_records_by_date_range"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product = Product.objects.first()
        HCParticipation.objects.filter(product=self.product).delete()
        self.user = Dojo_User.objects.get(username="admin")

    def _create_hc_with_create_date(self, create_date):
        hc = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.user,
        )
        HCParticipation.objects.filter(pk=hc.pk).update(create_date=create_date)
        return hc

    def test_requires_both_dates(self):
        with self.assertRaises(ValueError):
            delete_hc_participation_records_by_date_range(None, datetime.date(2026, 1, 1))

        with self.assertRaises(ValueError):
            delete_hc_participation_records_by_date_range(datetime.date(2026, 1, 1), None)

    def test_start_date_after_end_date_raises_error(self):
        with self.assertRaises(ValueError):
            delete_hc_participation_records_by_date_range(
                datetime.date(2026, 1, 10), datetime.date(2026, 1, 1),
            )

    def test_deletes_only_records_within_range(self):
        inside_start = self._create_hc_with_create_date(
            datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
        )
        inside_end = self._create_hc_with_create_date(
            datetime.datetime(2026, 1, 10, 12, 0, tzinfo=datetime.timezone.utc)
        )
        outside_before = self._create_hc_with_create_date(
            datetime.datetime(2025, 12, 31, 12, 0, tzinfo=datetime.timezone.utc)
        )
        outside_after = self._create_hc_with_create_date(
            datetime.datetime(2026, 1, 11, 12, 0, tzinfo=datetime.timezone.utc)
        )

        result = delete_hc_participation_records_by_date_range(
            datetime.date(2026, 1, 1), datetime.date(2026, 1, 10),
        )

        self.assertEqual(result["matched_records"], 2)
        self.assertFalse(HCParticipation.objects.filter(pk=inside_start.pk).exists())
        self.assertFalse(HCParticipation.objects.filter(pk=inside_end.pk).exists())
        self.assertTrue(HCParticipation.objects.filter(pk=outside_before.pk).exists())
        self.assertTrue(HCParticipation.objects.filter(pk=outside_after.pk).exists())

    def test_cascades_delete_of_related_logs(self):
        hc = self._create_hc_with_create_date(
            datetime.datetime(2026, 2, 1, 12, 0, tzinfo=datetime.timezone.utc)
        )
        HCParticipationLog.objects.create(
            hc_participation=hc,
            changed_by=self.user,
            current_status="Pending",
        )

        delete_hc_participation_records_by_date_range(
            datetime.date(2026, 2, 1), datetime.date(2026, 2, 1),
        )

        self.assertFalse(HCParticipationLog.objects.filter(hc_participation_id=hc.pk).exists())


class DeleteHCParticipationRecordsAPIViewTest(TestCase):
    """Tests for the delete-records API endpoint"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.client = APIClient()
        self.admin = Dojo_User.objects.get(username="admin")
        token, _created = Token.objects.get_or_create(user=self.admin)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.product = Product.objects.first()
        HCParticipation.objects.filter(product=self.product).delete()

        self.url = reverse("api_hc_delete_records")

    def test_requires_authentication(self):
        api_client = APIClient()

        response = api_client.post(self.url, data={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }, format="json")

        self.assertEqual(response.status_code, 403)

    def test_forbids_non_staff_user(self):
        regular_user = Dojo_User.objects.create_user(
            username="hc_delete_regular_user",
            email="hc_delete_regular_user@test.com",
            password="testpass123",
            is_staff=False,
        )
        regular_token = Token.objects.create(user=regular_user)
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Token " + regular_token.key)

        response = api_client.post(self.url, data={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["status"], "forbidden")

    def test_missing_dates_returns_bad_request(self):
        response = self.client.post(self.url, data={}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "bad_request")

    def test_invalid_date_format_returns_bad_request(self):
        response = self.client.post(self.url, data={
            "start_date": "not-a-date",
            "end_date": "2026-01-31",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "bad_request")

    def test_start_after_end_date_returns_bad_request(self):
        response = self.client.post(self.url, data={
            "start_date": "2026-01-31",
            "end_date": "2026-01-01",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "bad_request")

    def test_deletes_records_within_range(self):
        hc_in_range = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Pending",
            created_by=self.admin,
        )
        HCParticipation.objects.filter(pk=hc_in_range.pk).update(
            create_date=datetime.datetime(2026, 1, 15, 12, 0, tzinfo=datetime.timezone.utc)
        )

        response = self.client.post(self.url, data={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["data"]["matched_records"], 1)
        self.assertFalse(HCParticipation.objects.filter(pk=hc_in_range.pk).exists())


class ReturnHCParticipationToPendingAPIViewTest(TestCase):
    """Tests for the return-to-pending API endpoint"""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.client = APIClient()
        self.admin = Dojo_User.objects.get(username="admin")
        token, _created = Token.objects.get_or_create(user=self.admin)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.product = Product.objects.first()
        self.hc_request = HCParticipation.objects.create(
            product=self.product,
            recommendation="postulated",
            status="Reviewed",
            created_by=self.admin,
        )
        self.url = reverse("api_hc_return_to_pending", args=[str(self.hc_request.uuid)])

    def test_requires_authentication(self):
        api_client = APIClient()
        response = api_client.post(self.url, data={"reason": "test"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_forbids_non_admin_and_non_operative_user(self):
        regular_user = Dojo_User.objects.create_user(
            username="hc_return_regular_user",
            email="hc_return_regular_user@test.com",
            password="testpass123",
            is_staff=False,
            is_superuser=False,
        )
        regular_token = Token.objects.create(user=regular_user)
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Token " + regular_token.key)

        response = api_client.post(self.url, data={"reason": "test"}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["status"], "forbidden")

    @override_settings(OPERATIVE_USER="hc_oper_user")
    def test_allows_operative_user(self):
        operative_user = Dojo_User.objects.create_user(
            username="hc_oper_user",
            email="hc_oper_user@test.com",
            password="testpass123",
            is_staff=False,
            is_superuser=False,
        )
        operative_token = Token.objects.create(user=operative_user)
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Token " + operative_token.key)

        response = api_client.post(self.url, data={"reason": "operator reset"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.hc_request.refresh_from_db()
        self.assertEqual(self.hc_request.status, "Pending")
