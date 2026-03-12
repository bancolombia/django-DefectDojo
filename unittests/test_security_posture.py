from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch

from dojo.models import (
    Product, 
    Engagement, 
    Test, 
    Finding,
    GeneralSettings,
    Product_Type,
)

class SecurityPostureAPITest(TestCase):
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        """Initial configuration for tests"""
        self.client = APIClient()
        
        # Create test user
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.url = reverse('engagement_security_posture')
        
        # Create test data
        self.product_type = Product_Type.objects.get(id=1)
        self.product = Product.objects.first()
        self.engagement = Engagement.objects.first()
        self.engagement.name = "Test Engagement for Security Posture"
        self.engagement.save()
        self.test = Test.objects.first()
        
        # Create test findings
        self.critical_finding = Finding.objects.create(
            title="Critical Security Issue",
            test=self.test,
            severity="Critical",
            description="A critical security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False
        )
        self.critical_finding.save()
        
        self.high_finding = Finding.objects.create(
            title="High Security Issue",
            test=self.test,
            severity="High", 
            description="A high security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False
        )
        self.high_finding.save()
        
        
        self.medium_finding = Finding.objects.create(
            title="Medium Security Issue",
            test=self.test,
            severity="Medium",
            description="A medium security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False
        )
        self.medium_finding.save()
        
        
        self.setup_general_settings()
        
        self.url = reverse('engagement_security_posture')

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
                'value': '["hacking_continuous", "red_team", "pentest"]',
                'data_type': 'LIST'
            }
        )
        
        GeneralSettings.objects.get_or_create(
            name_key='DEVSECOPS_ADOPTION_INCLUDE_TAGS',
            defaults={
                'value': '["engine_iac", "engine_container"]',
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
        

    def test_get_security_posture_with_engagement_id(self):
        """Test get security posture with valid engagement_id"""
        response = self.client.get(
            self.url,
            {'engagement_id': self.engagement.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.json())
        
        data = response.json()['data']
        self.assertEqual(data['engagement_name'], self.engagement.name)
        self.assertEqual(data['engagement_id'], self.engagement.id)
        self.assertEqual(data['severity_product'], self.product.business_criticality)
        self.assertIn('very_critical', data['counter_findings_by_priority'])
        self.assertIn('critical', data['counter_findings_by_priority'])
        self.assertIn('high', data['counter_findings_by_priority'])
        self.assertIn('medium_low', data['counter_findings_by_priority'])
        self.assertIn('counter_active_findings', data)
        self.assertIn('counter_total_findings', data)
        self.assertIn('counter_accepted_findings', data)
        self.assertIn('counter_closed_findings', data)
        self.assertIn('counter_transferred_findings', data)
        self.assertIn('counter_onwhitelist_findings', data)

    def test_get_security_posture_with_engagement_name(self):
        """Test get security posture with valid engagement_name"""
        response = self.client.get(
            f"{self.url}?engagement_name={self.engagement.name}",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(data['engagement_name'], self.engagement.name)

    def test_get_security_posture_invalid_engagement_id(self):
        """Test error with non-existent engagement_id"""
        response = self.client.get(
            self.url,
            {'engagement_id': 99999},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid pk "99999" - object does not exist.',
                      response.json()['data']["engagement_id"])

    def test_get_security_posture_invalid_engagement_name(self):
        """Test error with non-existent engagement_name"""
        response = self.client.get(
            self.url,
            {'engagement_name': 'NonExistentEngagement'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_security_posture_findings_count(self):
        """Test that findings counts are correct"""
        response = self.client.get(
            self.url,
            {'engagement_id': self.engagement.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        
        self.assertEqual(data['counter_findings_by_priority']['very_critical'], 0)
        self.assertEqual(data['counter_findings_by_priority']['critical'], 0)
        self.assertEqual(data['counter_findings_by_priority']['high'], 0)
        self.assertEqual(data['counter_findings_by_priority']['medium_low'], 0)
        self.assertEqual(data['counter_findings_by_priority']['unknown'], 4)


class ProductSecurityPostureAPITest(TestCase):
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        """Initial configuration for product security posture tests"""
        self.client = APIClient()
        
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.url = reverse('product_security_posture')
        
        self.product_type = Product_Type.objects.get(id=1)
        self.product = Product.objects.first()
        self.product.name = "Test Product for Security Posture"
        self.product.business_criticality = "high"
        self.product.save()
        
        self.engagement = Engagement.objects.first()
        self.engagement.product = self.product
        self.engagement.active = True
        self.engagement.save()
        
        self.test = Test.objects.first()
        
        self.critical_finding = Finding.objects.create(
            title="Critical Security Issue Product",
            test=self.test,
            severity="Critical",
            description="A critical security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False
        )
        self.critical_finding.save()
        
        self.high_finding = Finding.objects.create(
            title="High Security Issue Product",
            test=self.test,
            severity="High", 
            description="A high security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False
        )
        self.high_finding.save()
        
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
                'value': '["hacking_continuous", "red_team", "pentest"]',
                'data_type': 'LIST'
            }
        )
        
        GeneralSettings.objects.get_or_create(
            name_key='DEVSECOPS_ADOPTION_INCLUDE_TAGS',
            defaults={
                'value': '["engine_iac", "engine_container"]',
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
        

    def test_get_product_security_posture_with_product_id(self):
        """Test get product security posture with valid product_id"""
        response = self.client.get(
            self.url,
            {'product_id': self.product.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.json())
        
        data = response.json()['data']
        self.assertEqual(data['product_name'], self.product.name)
        self.assertEqual(data['product_id'], self.product.id)
        self.assertEqual(data['severity_product'], self.product.business_criticality)
        self.assertIn('counter_active_findings', data)
        self.assertIn('counter_total_findings', data)
        self.assertIn('counter_accepted_findings', data)
        self.assertIn('counter_closed_findings', data)
        self.assertIn('counter_transferred_findings', data)
        self.assertIn('counter_onwhitelist_findings', data)
        self.assertIn('counter_findings_by_priority', data)
        self.assertIn('counter_findings_by_severity', data)
        self.assertIn('adoption_devsecops', data)

    def test_get_product_security_posture_with_product_name(self):
        """Test get product security posture with valid product_name"""
        response = self.client.get(
            f"{self.url}?product_name={self.product.name}",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(data['product_name'], self.product.name)

    def test_get_product_security_posture_missing_parameters(self):
        """Test error when required parameters are missing"""
        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Either product_id or product_name must be provided', 
                     response.json()['data']["non_field_errors"])

    def test_get_product_security_posture_invalid_product_id(self):
        """Test error with non-existent product_id"""
        response = self.client.get(
            self.url,
            {'product_id': 99999},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid pk "99999" - object does not exist.',
                      response.json()['data']["product_id"])

    def test_get_product_security_posture_invalid_product_name(self):
        """Test error with non-existent product_name"""
        response = self.client.get(
            self.url,
            {'product_name': 'NonExistentProduct'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_product_security_posture_findings_count(self):
        """Test that findings counts are aggregated correctly"""
        response = self.client.get(
            self.url,
            {'product_id': self.product.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        
        self.assertIn('very_critical', data['counter_findings_by_priority'])
        self.assertIn('critical', data['counter_findings_by_priority'])
        self.assertIn('high', data['counter_findings_by_priority'])
        self.assertIn('medium_low', data['counter_findings_by_priority'])
        self.assertIn('unknown', data['counter_findings_by_priority'])

    def test_get_product_security_posture_severity_count(self):
        """Test that severity counts are aggregated correctly"""
        response = self.client.get(
            self.url,
            {'product_id': self.product.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        
        self.assertIn('critical', data['counter_findings_by_severity'])
        self.assertIn('high', data['counter_findings_by_severity'])
        self.assertIn('medium', data['counter_findings_by_severity'])
        self.assertIn('low', data['counter_findings_by_severity'])
        self.assertIn('info', data['counter_findings_by_severity'])

    def test_get_product_security_posture_has_result_and_status(self):
        """Test that result and status are present in response"""
        response = self.client.get(
            self.url,
            {'product_id': self.product.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        
        self.assertIn('result', data)
        self.assertIn('status', data)
        self.assertIsInstance(data['result'], (int, float))
        self.assertIsInstance(data['status'], str)

    def test_get_product_security_posture_hacking_continuous(self):
        """Test that hacking continuous fields are present"""
        response = self.client.get(
            self.url,
            {'product_id': self.product.id},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        
        self.assertIn('is_in_hacking_continuos', data)
        self.assertIn('events_active_hacking', data)
        self.assertIn('status', data['events_active_hacking'])
        self.assertIn('events', data['events_active_hacking'])


class ProductTypeSecurityPostureAPITest(TestCase):
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        """Initial configuration for product type security posture tests"""
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.url = reverse('product_type_security_posture_events')

        self.product_type = Product_Type.objects.get(id=1)
        self.product_type.name = "Test Product Type for Security Posture"
        self.product_type.save()

        self.product = Product.objects.first()
        self.product.name = "Product Under Product Type"
        self.product.prod_type = self.product_type
        self.product.active = True
        self.product.save()

        self.engagement = Engagement.objects.first()
        self.engagement.product = self.product
        self.engagement.active = True
        self.engagement.save()

        self.test = Test.objects.first()

        Finding.objects.create(
            title="Critical Security Issue Product Type",
            test=self.test,
            severity="Critical",
            description="A critical security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False,
        )

        Finding.objects.create(
            title="High Security Issue Product Type",
            test=self.test,
            severity="High",
            description="A high security vulnerability",
            active=True,
            verified=True,
            false_p=False,
            duplicate=False,
        )

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
                'value': '["hacking_continuous", "red_team", "pentest"]',
                'data_type': 'LIST'
            }
        )

        GeneralSettings.objects.get_or_create(
            name_key='DEVSECOPS_ADOPTION_INCLUDE_TAGS',
            defaults={
                'value': '["engine_iac", "engine_container"]',
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

        GeneralSettings.objects.get_or_create(
            name_key='HACKING_CONTINUOUS_EVENT_TAGS',
            defaults={
                'value': '["event_hacking", "active_event"]',
                'data_type': 'LIST'
            }
        )

    def test_get_product_type_security_posture_with_product_type_id(self):
        """Test get product type security posture with valid product_type_id"""
        response = self.client.get(
            self.url,
            {'product_type_id': self.product_type.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.json())

        data = response.json()['data']
        self.assertEqual(data['product_type_id'], self.product_type.id)
        self.assertEqual(data['product_type_name'], self.product_type.name)
        self.assertIn('counter_active_findings', data)
        self.assertIn('counter_total_findings', data)
        self.assertIn('counter_accepted_findings', data)
        self.assertIn('counter_closed_findings', data)
        self.assertIn('counter_transferred_findings', data)
        self.assertIn('counter_onwhitelist_findings', data)
        self.assertIn('counter_findings_by_priority', data)
        self.assertIn('counter_findings_by_severity', data)

    def test_get_product_type_security_posture_with_product_type_name(self):
        """Test get product type security posture with valid product_type_name"""
        response = self.client.get(
            f"{self.url}?product_type_name={self.product_type.name}",
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(data['product_type_name'], self.product_type.name)

    def test_get_product_type_security_posture_missing_parameters(self):
        """Test error when required parameters are missing"""
        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            'Either product_type_id or product_type_name must be provided',
            response.json()['data']["non_field_errors"],
        )

    def test_get_product_type_security_posture_invalid_product_type_id(self):
        """Test error with non-existent product_type_id"""
        response = self.client.get(
            self.url,
            {'product_type_id': 99999},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            'Invalid pk "99999" - object does not exist.',
            response.json()['data']["product_type_id"],
        )

    def test_get_product_type_security_posture_invalid_product_type_name(self):
        """Test error with non-existent product_type_name"""
        response = self.client.get(
            self.url,
            {'product_type_name': 'NonExistentProductType'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_product_type_security_posture_findings_count(self):
        """Test that findings count keys are present"""
        response = self.client.get(
            self.url,
            {'product_type_id': self.product_type.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']

        self.assertIn('very_critical', data['counter_findings_by_priority'])
        self.assertIn('critical', data['counter_findings_by_priority'])
        self.assertIn('high', data['counter_findings_by_priority'])
        self.assertIn('medium_low', data['counter_findings_by_priority'])
        self.assertIn('unknown', data['counter_findings_by_priority'])

    def test_get_product_type_security_posture_severity_count(self):
        """Test that severity count keys are present"""
        response = self.client.get(
            self.url,
            {'product_type_id': self.product_type.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']

        self.assertIn('critical', data['counter_findings_by_severity'])
        self.assertIn('high', data['counter_findings_by_severity'])
        self.assertIn('medium', data['counter_findings_by_severity'])
        self.assertIn('low', data['counter_findings_by_severity'])
        self.assertIn('info', data['counter_findings_by_severity'])

    def test_get_product_type_security_posture_has_result_and_status(self):
        """Test that result and status are present in response"""
        response = self.client.get(
            self.url,
            {'product_type_id': self.product_type.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']

        self.assertIn('result', data)
        self.assertIn('status', data)
        self.assertIsInstance(data['result'], (int, float))
        self.assertIsInstance(data['status'], str)

