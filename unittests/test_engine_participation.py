"""
Tests for HC (Hacking Continuo) Participation module.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock

from dojo.models import (
    Product, 
    Product_Type,
    GeneralSettings,
    Dojo_User,
)
from dojo.engine_participation.models import (
    HCParticipation,
    HCParticipationDiscussion,
    HCParticipationLog,
)
from dojo.engine_participation.helpers import (
    evaluate_product_for_hc,
    run_hc_participation_evaluation,
    get_latest_hc_evaluation_for_product,
    ELIGIBLE_CRITICALITIES,
    HC_BMC_APPLICATION_CLASSID_MARKER,
    InvalidHCParticipationTransition,
    approve_hc_participation,
    mark_hc_participation_reviewed,
    reject_hc_participation,
)


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


class EvaluateProductForHCTest(TestCase):
    """Tests for the evaluate_product_for_hc helper function"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.product = Product.objects.first()
        self.setup_general_settings()
    
    def setup_general_settings(self):
        """Configure GeneralSettings for tests"""
        GeneralSettings.objects.get_or_create(
            name_key='SECURITY_POSTURE_STATUS',
            defaults={
                'value': '{"APETITO": 50, "TOLERANCIA": 100, "EXCEDIDO": 150}',
                'data_type': 'DICT'
            }
        )
        GeneralSettings.objects.get_or_create(
            name_key='HACKING_CONTINUOUS_TAGS',
            defaults={
                'value': '["hacking_continuous"]',
                'data_type': 'LIST'
            }
        )
        GeneralSettings.objects.get_or_create(
            name_key='HACKING_CONTINUOUS_DAYS_TOLERANCE',
            defaults={
                'value': '30',
                'data_type': 'INT'
            }
        )
    
    def test_r1_not_eligible_low_criticality(self):
        """R1: Products with low criticality are not eligible"""
        self.product.business_criticality = "low"
        self.product.save()
        
        result = evaluate_product_for_hc(self.product)
        
        self.assertEqual(result["recommendation"], "not_eligible")
        self.assertIn("R1", result["reason"])
    
    def test_r1_not_eligible_none_criticality(self):
        """R1: Products with no criticality are not eligible"""
        self.product.business_criticality = None
        self.product.save()
        
        result = evaluate_product_for_hc(self.product)
        
        self.assertEqual(result["recommendation"], "not_eligible")
        self.assertIn("R1", result["reason"])
    
    def test_r1_eligible_high_criticality(self):
        """R1: Products with high criticality are eligible"""
        self.product.business_criticality = "high"
        self.product.save()
        
        result = evaluate_product_for_hc(self.product)
        
        self.assertIn(result["recommendation"], ["postulated", "already_in_hc"])
    
    def test_r1_eligible_medium_criticality(self):
        """R1: Products with medium criticality are eligible"""
        self.product.business_criticality = "medium"
        self.product.save()
        
        result = evaluate_product_for_hc(self.product)
        
        self.assertIn(result["recommendation"], ["postulated", "already_in_hc"])
    
    @patch('dojo.engine_participation.helpers.get_product_security_posture')
    def test_r2_already_in_hc(self, mock_security_posture):
        """R2: Products already in HC should be documented, not postulated"""
        self.product.business_criticality = "high"
        self.product.save()
        
        mock_security_posture.return_value = {
            "is_in_hacking_continuos": True,
            "counter_active_findings": 5,
            "counter_total_findings": 10,
            "adoption_devsecops": [],
            "result": 10.0,
            "status": "APETITO",
        }
        
        result = evaluate_product_for_hc(self.product)
        
        self.assertEqual(result["recommendation"], "already_in_hc")
        self.assertIn("R2", result["reason"])
        self.assertTrue(result["was_in_hacking_continuous"])
    
    @patch('dojo.engine_participation.helpers.get_product_security_posture')
    def test_r3_postulated(self, mock_security_posture):
        """R3: Eligible products not in HC should be postulated"""
        self.product.business_criticality = "high"
        self.product.save()
        
        mock_security_posture.return_value = {
            "is_in_hacking_continuos": False,
            "counter_active_findings": 5,
            "counter_total_findings": 10,
            "adoption_devsecops": ["engine_iac"],
            "result": 10.0,
            "status": "APETITO",
        }
        
        result = evaluate_product_for_hc(self.product)
        
        self.assertEqual(result["recommendation"], "postulated")
        self.assertIn("R3", result["reason"])
        self.assertFalse(result["was_in_hacking_continuous"])


class RunHCEvaluationTest(TestCase):
    """Tests for the run_hc_participation_evaluation function"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.user = Dojo_User.objects.get(username="admin")
        self.product = Product.objects.first()
        self.product.business_criticality = "high"
        self.product.description = f"Service Metadata | {HC_BMC_APPLICATION_CLASSID_MARKER}"
        self.product.save()
        self.setup_general_settings()
    
    def setup_general_settings(self):
        GeneralSettings.objects.get_or_create(
            name_key='SECURITY_POSTURE_STATUS',
            defaults={
                'value': '{"APETITO": 50, "TOLERANCIA": 100, "EXCEDIDO": 150}',
                'data_type': 'DICT'
            }
        )
        GeneralSettings.objects.get_or_create(
            name_key='HACKING_CONTINUOUS_TAGS',
            defaults={
                'value': '["hacking_continuous"]',
                'data_type': 'LIST'
            }
        )
    
    @patch('dojo.engine_participation.helpers.get_product_security_posture')
    def test_run_evaluation_creates_records(self, mock_security_posture):
        """Test that evaluation creates database records"""
        mock_security_posture.return_value = {
            "is_in_hacking_continuos": False,
            "counter_active_findings": 5,
            "counter_total_findings": 10,
            "adoption_devsecops": [],
            "result": 10.0,
            "status": "APETITO",
        }
        
        initial_count = HCParticipation.objects.count()
        
        result = run_hc_participation_evaluation(user=self.user)
        
        self.assertGreaterEqual(
            HCParticipation.objects.count(),
            initial_count
        )
        self.assertIsNotNone(result["batch_id"])
    
    @patch('dojo.engine_participation.helpers.get_product_security_posture')
    def test_run_evaluation_returns_summary(self, mock_security_posture):
        """Test that evaluation returns proper summary"""
        mock_security_posture.return_value = {
            "is_in_hacking_continuos": False,
            "counter_active_findings": 5,
            "counter_total_findings": 10,
            "adoption_devsecops": [],
            "result": 10.0,
            "status": "APETITO",
        }
        
        result = run_hc_participation_evaluation(user=self.user)
        
        self.assertIn("summary", result)
        self.assertIn("postulated", result["summary"])
        self.assertIn("already_in_hc", result["summary"])
        self.assertIn("not_eligible", result["summary"])
        self.assertIn("scope", result)
        self.assertIn("total_products", result["scope"])
        self.assertIn("classid_candidates", result["scope"])
        self.assertIn("skipped_by_classid", result["scope"])

    @patch('dojo.engine_participation.helpers.get_product_security_posture')
    def test_run_evaluation_skips_existing_active_request(self, mock_security_posture):
        """Test that evaluation does not duplicate active HC requests"""
        mock_security_posture.return_value = {
            "is_in_hacking_continuos": False,
            "counter_active_findings": 5,
            "counter_total_findings": 10,
            "adoption_devsecops": [],
            "result": 10.0,
            "status": "APETITO",
        }

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
    
    @patch('dojo.engine_participation.helpers.Product.objects')
    def test_run_evaluation_empty_products(self, mock_products):
        """Test evaluation with no products"""
        mock_products.count.return_value = 0
        mock_products.select_related.return_value.filter.return_value.count.return_value = 0
        mock_products.select_related.return_value.filter.return_value.all.return_value = []
        
        result = run_hc_participation_evaluation(user=self.user)
        
        self.assertEqual(result["total_evaluated"], 0)
        self.assertEqual(result["scope"]["total_products"], 0)
        self.assertEqual(result["scope"]["classid_candidates"], 0)
        self.assertEqual(result["scope"]["skipped_by_classid"], 0)


class ApproveRejectHCTest(TestCase):
    """Tests for approve and reject functions"""
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        self.product = Product.objects.first()
        self.user = Dojo_User.objects.get(username="admin")
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


class EligibleCriticalitiesTest(TestCase):
    """Tests for eligible criticalities constant"""
    
    def test_eligible_criticalities_values(self):
        """Test that eligible criticalities are correctly defined"""
        self.assertIn("very high", ELIGIBLE_CRITICALITIES)
        self.assertIn("high", ELIGIBLE_CRITICALITIES)
        self.assertIn("medium", ELIGIBLE_CRITICALITIES)
        
        self.assertNotIn("low", ELIGIBLE_CRITICALITIES)
        self.assertNotIn("very low", ELIGIBLE_CRITICALITIES)
        self.assertNotIn("none", ELIGIBLE_CRITICALITIES)


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
    
    def test_list_view(self):
        """Test HC participation list view"""
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        
        response = client.get(reverse('hc_participations'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
    
    def test_show_view(self):
        """Test HC participation detail view"""
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        
        response = client.get(reverse('hc_participation', args=[str(self.hc.uuid)]))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
    
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
