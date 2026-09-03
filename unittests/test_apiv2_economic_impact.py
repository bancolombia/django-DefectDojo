# from django.urls import reverse
# from rest_framework import status
# from rest_framework.authtoken.models import Token
# from rest_framework.test import APIClient, APITestCase
# from dojo.models import GeneralSettings

# from dojo.api_v2.long_risk_acceptance.models import (
#     RiskAcceptanceEngagement,
#     RiskAcceptanceEngagementEconomicImpact,
# )
# from dojo.models import Dojo_User, Product


# class EconomicImpactViewSetTestCase(APITestCase):
#     fixtures = ["dojo_testdata.json"]

#     def setUp(self):
#         token = Token.objects.get(user__username="admin")
#         self.client = APIClient()
#         self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
#         self.url = reverse("economic_impact-list")
#         GeneralSettings.objects.get_or_create(
#             name_key='CAUSE_LONG_RISK_ACCEPTANCE',
#             defaults={
#                 'value': 'CAUSE1,CAUSE2,CAUSE3',
#                 'data_type': 'LIST'
#             }
#         )

#         self.owner = Dojo_User.objects.get(username="admin")
#         self.product = Product.objects.get(id=1)
#         self.risk_acceptance_engagement = RiskAcceptanceEngagement.objects.create(
#             description="Long risk acceptance for API tests",
#             cause="CAUSE1",
#             owner=self.owner,
#             product=self.product,
#             reviewed_by=self.owner.username,
#         )

#     def _payload(self, **overrides):
#         data = {
#             "title": "Economic Impact Test",
#             "description": "Economic impact acceptance test",
#             "control_effectiveness": 80,
#             "economic_impact": 1345,
#             "risk_acceptance_engagement": self.risk_acceptance_engagement.id,
#         }
#         data.update(overrides)
#         return data

#     def _model_payload(self, **overrides):
#         data = {
#             "title": "Economic Impact Test",
#             "description": "Economic impact acceptance test",
#             "control_effectiveness": 80,
#             "economic_impact": 1345,
#             "risk_acceptance_engagement": self.risk_acceptance_engagement,
#         }
#         data.update(overrides)
#         return data

#     def test_create_economic_impact_success(self):
#         response = self.client.post(self.url, self._payload(), format="json")
#         self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
#         self.assertEqual(response.data["control_effectiveness"], 80, response.data)
#         self.assertEqual(response.data["economic_impact"], 1345, response.data)
#         self.assertEqual(
#             response.data["risk_acceptance_engagement"],
#             self.risk_acceptance_engagement.id,
#             response.data,
#         )

#     def test_create_economic_impact_rejects_control_effectiveness_above_100(self):
#         response = self.client.post(
#             self.url,
#             self._payload(control_effectiveness=101),
#             format="json",
#         )
#         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
#         self.assertIn("control_effectiveness", response.data, response.data)

#     def test_create_economic_impact_rejects_control_effectiveness_below_0(self):
#         response = self.client.post(
#             self.url,
#             self._payload(control_effectiveness=-1),
#             format="json",
#         )
#         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
#         self.assertIn("control_effectiveness", response.data, response.data)

#     def test_list_economic_impact_success(self):
#         RiskAcceptanceEngagementEconomicImpact.objects.create(**self._model_payload())
#         response = self.client.get(self.url)
#         self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
#         self.assertIn("results", response.data, response.data)
#         self.assertGreaterEqual(len(response.data["results"]), 1, response.data)

#     def test_retrieve_economic_impact_success(self):
#         impact = RiskAcceptanceEngagementEconomicImpact.objects.create(**self._model_payload())
#         response = self.client.get(reverse("economic_impact-detail", args=[impact.id]))
#         self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
#         self.assertEqual(response.data["id"], impact.id, response.data)
#         self.assertEqual(response.data["control_effectiveness"], 80, response.data)
