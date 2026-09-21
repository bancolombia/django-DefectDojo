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
from dojo.api_v2.risk_posture.helper import (
    _apply_total_counters,
    _classify_active_findings,
    _init_priority_counter,
    _init_severity_counter,
    _increment_bucket,
    calculate_posture,
    adoption_devsecops_include,
    get_product_risk_posture,
    get_product_type_risk_posture,
    get_engagement_risk_posture,
)

class RiskPostureAPITest(TestCase):
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        """Initial configuration for tests"""
        self.client = APIClient()
        
        # Create test user
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.url = reverse('engagement_risk_posture')
        
        # Create test data
        self.product_type = Product_Type.objects.get(id=1)
        self.product = Product.objects.first()
        self.engagement = Engagement.objects.first()
        self.engagement.name = "Test Engagement for Risk Posture"
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
        
        self.url = reverse('engagement_risk_posture')

    def setup_general_settings(self):
        """Configure GeneralSettings for tests"""
        GeneralSettings.objects.get_or_create(
            name_key='RISK_POSTURE_STATUS',
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
        

    def test_get_risk_posture_with_engagement_id(self):
        """Test get risk posture with valid engagement_id"""
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

    def test_get_risk_posture_with_engagement_name(self):
        """Test get risk posture with valid engagement_name"""
        response = self.client.get(
            f"{self.url}?engagement_name={self.engagement.name}",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(data['engagement_name'], self.engagement.name)

    def test_get_risk_posture_missing_parameters(self):
        """Test error when required parameters are missing"""
        response = self.client.get(self.url, format='json')
        print("response", response.json())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Either engagement_id or engagement_name must be provided', 
                     response.json()['data']["non_field_errors"])

    def test_get_risk_posture_invalid_engagement_id(self):
        """Test error with non-existent engagement_id"""
        response = self.client.get(
            self.url,
            {'engagement_id': 99999},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid pk "99999" - object does not exist.',
                      response.json()['data']["engagement_id"])

    def test_get_risk_posture_invalid_engagement_name(self):
        """Test error with non-existent engagement_name"""
        response = self.client.get(
            self.url,
            {'engagement_name': 'NonExistentEngagement'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_risk_posture_findings_count(self):
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


class ProductRiskPostureAPITest(TestCase):
    fixtures = ['dojo_testdata.json']
    
    def setUp(self):
        """Initial configuration for product risk posture tests"""
        self.client = APIClient()
        
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.url = reverse('product_risk_posture')
        
        self.product_type = Product_Type.objects.get(id=1)
        self.product = Product.objects.first()
        self.product.name = "Test Product for Risk Posture"
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
            name_key='RISK_POSTURE_STATUS',
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
        

    def test_get_product_risk_posture_with_product_id(self):
        """Test get product risk posture with valid product_id"""
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

    def test_get_product_risk_posture_with_product_name(self):
        """Test get product risk posture with valid product_name"""
        response = self.client.get(
            f"{self.url}?product_name={self.product.name}",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(data['product_name'], self.product.name)

    def test_get_product_risk_posture_missing_parameters(self):
        """Test error when required parameters are missing"""
        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Either product_id or product_name must be provided', 
                     response.json()['data']["non_field_errors"])

    def test_get_product_risk_posture_invalid_product_id(self):
        """Test error with non-existent product_id"""
        response = self.client.get(
            self.url,
            {'product_id': 99999},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid pk "99999" - object does not exist.',
                      response.json()['data']["product_id"])

    def test_get_product_risk_posture_invalid_product_name(self):
        """Test error with non-existent product_name"""
        response = self.client.get(
            self.url,
            {'product_name': 'NonExistentProduct'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_product_risk_posture_findings_count(self):
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

    def test_get_product_risk_posture_severity_count(self):
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

    def test_get_product_risk_posture_has_result_and_status(self):
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

    def test_get_product_risk_posture_hacking_continuous(self):
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


class ProductTypeRiskPostureAPITest(TestCase):
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        """Initial configuration for product type risk posture tests"""
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.url = reverse('product_type_risk_posture_events')

        self.product_type = Product_Type.objects.get(id=1)
        self.product_type.name = "Test Product Type for Risk Posture"
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
            name_key='RISK_POSTURE_STATUS',
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

    def test_get_product_type_risk_posture_with_product_type_id(self):
        """Test get product type risk posture with valid product_type_id"""
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

    def test_get_product_type_risk_posture_with_product_type_name(self):
        """Test get product type risk posture with valid product_type_name"""
        response = self.client.get(
            f"{self.url}?product_type_name={self.product_type.name}",
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(data['product_type_name'], self.product_type.name)

    def test_get_product_type_risk_posture_missing_parameters(self):
        """Test error when required parameters are missing"""
        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            'Either product_type_id or product_type_name must be provided',
            response.json()['data']["non_field_errors"],
        )

    def test_get_product_type_risk_posture_invalid_product_type_id(self):
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

    def test_get_product_type_risk_posture_invalid_product_type_name(self):
        """Test error with non-existent product_type_name"""
        response = self.client.get(
            self.url,
            {'product_type_name': 'NonExistentProductType'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_product_type_risk_posture_findings_count(self):
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

    def test_get_product_type_risk_posture_severity_count(self):
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

    def test_get_product_type_risk_posture_has_result_and_status(self):
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


class RiskPostureHelperUnitTest(TestCase):
    """Unit tests para funciones helper del refactor ORM-aggregation."""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.engagement = Engagement.objects.first()
        self.test_obj = Test.objects.first()
        self._setup_general_settings()

    def _setup_general_settings(self):
        defaults = [
            ('RISK_POSTURE_STATUS', '{"APETITO": 50, "TOLERANCIA": 100, "EXCEDIDO": 150}', 'DICT'),
            ('HACKING_CONTINUOUS_TAGS', 'hacking_continuous', 'LIST'),
            ('DEVSECOPS_ADOPTION_INCLUDE_TAGS', 'engine_iac,engine_container', 'LIST'),
            ('HACKING_CONTINUOUS_DAYS_TOLERANCE', '30', 'INT'),
            ('HACKING_CONTINUOUS_EVENT_TAGS', '', 'LIST'),
        ]
        for key, value, dtype in defaults:
            GeneralSettings.objects.update_or_create(
                name_key=key, defaults={'value': value, 'data_type': dtype}
            )

    # --- _init_priority_counter / _init_severity_counter ---

    def test_init_priority_counter_all_zero(self):
        counter = _init_priority_counter()
        self.assertEqual(set(counter.keys()), {'very_critical', 'critical', 'high', 'medium_low', 'unknown'})
        self.assertTrue(all(v == 0 for v in counter.values()))

    def test_init_severity_counter_all_zero(self):
        counter = _init_severity_counter()
        self.assertEqual(set(counter.keys()), {'critical', 'high', 'medium', 'low', 'info', 'unknown'})
        self.assertTrue(all(v == 0 for v in counter.values()))

    # --- _increment_bucket ---

    def test_increment_bucket_very_critical(self):
        counter = _init_priority_counter()
        _increment_bucket(counter, 'Very Critical')
        self.assertEqual(counter['very_critical'], 1)

    def test_increment_bucket_unknown_fallback(self):
        """Claves que no existen en el counter deben caer a 'unknown'."""
        counter = _init_priority_counter()
        _increment_bucket(counter, 'NonExistentLevel')
        self.assertEqual(counter['unknown'], 1)

    def test_increment_bucket_severity_critical(self):
        counter = _init_severity_counter()
        _increment_bucket(counter, 'Critical')
        self.assertEqual(counter['critical'], 1)

    # --- calculate_posture ---

    def test_calculate_posture_returns_string(self):
        self.assertIsInstance(calculate_posture(10.0), str)

    def test_calculate_posture_unknown_when_no_settings(self):
        with patch.object(GeneralSettings, 'get_value', return_value={}):
            self.assertEqual(calculate_posture(0.0), 'UNKNOWN')

    def test_calculate_posture_first_matching_key(self):
        """Un resultado <= 50 debe retornar la primera clave (APETITO)."""
        result = calculate_posture(0.0)
        self.assertEqual(result, 'APETITO')

    # --- adoption_devsecops_include ---

    def test_adoption_devsecops_include_filters_correctly(self):
        tags = ['engine_iac', 'engine_container', 'unrelated_tag']
        result = adoption_devsecops_include(tags)
        self.assertIn('engine_iac', result)
        self.assertIn('engine_container', result)
        self.assertNotIn('unrelated_tag', result)

    def test_adoption_devsecops_include_empty(self):
        self.assertEqual(adoption_devsecops_include([]), [])

    def test_adoption_devsecops_include_deduplicates(self):
        tags = ['engine_iac', 'engine_iac', 'engine_container']
        result = adoption_devsecops_include(tags)
        self.assertEqual(len(result), len(set(result)))

    # --- _apply_total_counters (1 query aggregate) ---

    def test_apply_total_counters_all_keys_present(self):
        qs = Finding.objects.filter(test__engagement=self.engagement)
        data = {}
        _apply_total_counters(data, qs)
        for key in ('counter_active_findings', 'counter_total_findings',
                    'counter_closed_findings', 'counter_accepted_findings',
                    'counter_transferred_findings', 'counter_onwhitelist_findings'):
            self.assertIn(key, data)
            self.assertIsInstance(data[key], int)

    def test_apply_total_counters_active_finding_counted(self):
        """Un nuevo finding activo debe incrementar counter_active_findings."""
        before_qs = Finding.objects.filter(test__engagement=self.engagement)
        before_data = {}
        _apply_total_counters(before_data, before_qs)
        before_count = before_data['counter_active_findings']

        Finding.objects.create(
            title="New Active TC", test=self.test_obj, severity="High",
            description="d", active=True, verified=True, false_p=False, duplicate=False,
        )
        after_qs = Finding.objects.filter(test__engagement=self.engagement)
        after_data = {}
        _apply_total_counters(after_data, after_qs)
        self.assertEqual(after_data['counter_active_findings'], before_count + 1)

    def test_apply_total_counters_duplicate_not_counted_as_active(self):
        """Findings duplicados no deben contarse en counter_active_findings."""
        Finding.objects.create(
            title="Duplicate TC", test=self.test_obj, severity="High",
            description="d", active=True, duplicate=True, verified=True, false_p=False,
        )
        qs = Finding.objects.filter(test__engagement=self.engagement)
        data = {}
        _apply_total_counters(data, qs)
        # duplicate=True excluye del conteo activo
        active_manual = Finding.objects.filter(
            test__engagement=self.engagement,
            active=True, duplicate=False, risk_accepted=False
        ).count()
        self.assertEqual(data['counter_active_findings'], active_manual)

    # --- _classify_active_findings ---

    def test_classify_active_findings_returns_float(self):
        Finding.objects.create(
            title="Classify TC", test=self.test_obj, severity="Critical",
            description="d", active=True, verified=True, false_p=False, duplicate=False,
        )
        qs = Finding.objects.filter(
            test__engagement=self.engagement,
            active=True, duplicate=False, risk_accepted=False,
        )
        data = {
            'counter_findings_by_priority': _init_priority_counter(),
            'counter_findings_by_severity': _init_severity_counter(),
        }
        result = _classify_active_findings(data, qs)
        self.assertIsInstance(result, float)

    def test_classify_active_findings_total_matches_qs_count(self):
        """La suma de todos los buckets debe igual al total de findings activos."""
        Finding.objects.create(
            title="Classify High TC", test=self.test_obj, severity="High",
            description="d", active=True, verified=True, false_p=False, duplicate=False,
        )
        qs = Finding.objects.filter(
            test__engagement=self.engagement,
            active=True, duplicate=False, risk_accepted=False,
        )
        data = {
            'counter_findings_by_priority': _init_priority_counter(),
            'counter_findings_by_severity': _init_severity_counter(),
        }
        _classify_active_findings(data, qs)
        self.assertEqual(sum(data['counter_findings_by_severity'].values()), qs.count())
        self.assertEqual(sum(data['counter_findings_by_priority'].values()), qs.count())


class ProductPostureInactiveEngagementTest(TestCase):
    """Verifica que engagements inactivos son excluidos del cálculo del product posture."""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product = Product.objects.first()
        self.test_obj = Test.objects.first()
        # Desactivar todos los engagements del product para aislar el test
        Engagement.objects.filter(product=self.product).update(active=False)
        Finding.objects.create(
            title="Finding in inactive eng", test=self.test_obj, severity="Critical",
            description="d", active=True, verified=True, false_p=False, duplicate=False,
        )
        self._setup_general_settings()

    def _setup_general_settings(self):
        defaults = [
            ('RISK_POSTURE_STATUS', '{"APETITO": 50, "TOLERANCIA": 100}', 'DICT'),
            ('HACKING_CONTINUOUS_TAGS', '[]', 'LIST'),
            ('DEVSECOPS_ADOPTION_INCLUDE_TAGS', '["engine_iac"]', 'LIST'),
            ('HACKING_CONTINUOUS_DAYS_TOLERANCE', '30', 'INT'),
            ('HACKING_CONTINUOUS_EVENT_TAGS', '[]', 'LIST'),
        ]
        for key, value, dtype in defaults:
            GeneralSettings.objects.update_or_create(
                name_key=key, defaults={'value': value, 'data_type': dtype}
            )

    def test_inactive_engagement_findings_not_counted(self):
        """Findings de engagements inactivos no deben aparecer en counter_active_findings."""
        data = get_product_risk_posture(self.product, None)
        self.assertEqual(data['counter_active_findings'], 0)
        self.assertEqual(data['result'], 0.0)

    def test_inactive_engagement_fast_path_fields(self):
        """Con 0 engagements activos, todos los campos deben existir con valores por defecto."""
        data = get_product_risk_posture(self.product, None)
        self.assertIn('status', data)
        self.assertIn('adoption_devsecops', data)
        self.assertEqual(data['adoption_devsecops'], [])
        self.assertEqual(data['counter_total_findings'], 0)


class ProductTypePostureEmptyEngagementsTest(TestCase):
    """Verifica el fast-path cuando product_type no tiene engagements activos."""
    fixtures = ['dojo_testdata.json']

    def setUp(self):
        self.product_type = Product_Type.objects.get(id=1)
        Engagement.objects.filter(product__prod_type=self.product_type).update(active=False)
        self._setup_general_settings()

    def _setup_general_settings(self):
        defaults = [
            ('RISK_POSTURE_STATUS', '{"APETITO": 50, "TOLERANCIA": 100}', 'DICT'),
            ('HACKING_CONTINUOUS_TAGS', '[]', 'LIST'),
            ('DEVSECOPS_ADOPTION_INCLUDE_TAGS', '["engine_iac"]', 'LIST'),
            ('HACKING_CONTINUOUS_DAYS_TOLERANCE', '30', 'INT'),
            ('HACKING_CONTINUOUS_EVENT_TAGS', '[]', 'LIST'),
        ]
        for key, value, dtype in defaults:
            GeneralSettings.objects.update_or_create(
                name_key=key, defaults={'value': value, 'data_type': dtype}
            )

    def test_empty_engagements_returns_zeros(self):
        data = get_product_type_risk_posture(self.product_type, None)
        self.assertEqual(data['counter_active_findings'], 0)
        self.assertEqual(data['counter_total_findings'], 0)
        self.assertEqual(data['result'], 0.0)

    def test_empty_engagements_status_present(self):
        data = get_product_type_risk_posture(self.product_type, None)
        self.assertIn('status', data)
        self.assertIsInstance(data['status'], str)

    def test_empty_engagements_adoption_devsecops_empty(self):
        data = get_product_type_risk_posture(self.product_type, None)
        self.assertIn('adoption_devsecops', data)
        self.assertEqual(data['adoption_devsecops'], [])

