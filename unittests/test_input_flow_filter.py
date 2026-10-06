from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from dojo.api_v2.scope.models import InputFlow


class InputFlowProductFilterTestCase(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        # engagements 1 and 3 -> product 2, engagement 2 -> product 1
        self.flow_eng1 = InputFlow.objects.create(flowName="eng1", engagement_id=1)
        self.flow_eng3 = InputFlow.objects.create(flowName="eng3", engagement_id=3)
        self.flow_eng2 = InputFlow.objects.create(flowName="eng2", engagement_id=2)

    def flow_ids(self, query):
        response = self.client.get(f"/api/v2/input_flow/?{query}&limit=100")
        assert response.status_code == status.HTTP_200_OK, response.data
        return {flow["id"] for flow in response.data["results"]}

    def test_filter_by_product(self):
        assert self.flow_ids("product=2") == {self.flow_eng1.id, self.flow_eng3.id}
        assert self.flow_ids("product=1") == {self.flow_eng2.id}

    def test_filter_by_product_and_engagement(self):
        assert self.flow_ids("product=2&engagement=3") == {self.flow_eng3.id}

    def test_filter_by_engagement_still_works(self):
        assert self.flow_ids("engagement=1") == {self.flow_eng1.id}
