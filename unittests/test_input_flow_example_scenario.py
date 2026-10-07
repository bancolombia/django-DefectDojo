from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from dojo.api_v2.scope.models import InputFlow, InputScenario, InputURL
from dojo.api_v2.scope.serializers import EXAMPLE_SCENARIO_DESCRIPTION, EXAMPLE_SCENARIO_ESTIMATED_TIME
from dojo.models import Dojo_User, Product_Member, Role


class InputFlowExampleScenarioTestCase(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        token = Token.objects.get(user__username="admin")
        self.admin = token.user
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        self.flow = InputFlow.objects.create(flowName="flow", engagement_id=1)

    def scenario_payload(self, **kwargs):
        payload = {"estimated_time": 10, "description": "custom", "status": "untested"}
        payload.update(kwargs)
        return payload

    def assert_is_example(self, scenario, user):
        assert scenario.estimated_time == EXAMPLE_SCENARIO_ESTIMATED_TIME
        assert scenario.description == EXAMPLE_SCENARIO_DESCRIPTION
        assert scenario.status == "untested"
        assert scenario.designed_by == user

    # creation

    def test_create_flow_url_without_scenarios_gets_example(self):
        response = self.client.post(
            "/api/v2/input_flow/",
            {"flowName": "new", "engagement": 1, "urls": [{"url": "https://example.com/a"}]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        url = InputURL.objects.get(id=response.data["data"]["urls"][0]["id"])
        assert url.scenarios.count() == 1
        self.assert_is_example(url.scenarios.get(), self.admin)
        assert len(response.data["data"]["urls"][0]["scenarios"]) == 1

    def test_create_flow_url_with_scenarios_gets_no_example(self):
        response = self.client.post(
            "/api/v2/input_flow/",
            {
                "flowName": "new",
                "engagement": 1,
                "urls": [{"url": "https://example.com/a", "scenarios": [self.scenario_payload()]}],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        url = InputURL.objects.get(id=response.data["data"]["urls"][0]["id"])
        assert list(url.scenarios.values_list("description", flat=True)) == ["custom"]

    def test_create_flow_without_urls_creates_nothing(self):
        response = self.client.post(
            "/api/v2/input_flow/", {"flowName": "empty", "engagement": 1}, format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        flow = InputFlow.objects.get(id=response.data["data"]["id"])
        assert flow.urls.count() == 0

    def test_add_url_without_scenarios_gets_example(self):
        response = self.client.post(
            f"/api/v2/input_flow/{self.flow.id}/add_url/", {"url": "https://example.com/b"}, format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        url = InputURL.objects.get(id=response.data["data"]["id"])
        self.assert_is_example(url.scenarios.get(), self.admin)

    def test_add_url_with_scenarios_gets_no_example(self):
        response = self.client.post(
            f"/api/v2/input_flow/{self.flow.id}/add_url/",
            {"url": "https://example.com/b", "scenarios": [self.scenario_payload()]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        url = InputURL.objects.get(id=response.data["data"]["id"])
        assert list(url.scenarios.values_list("description", flat=True)) == ["custom"]

    def test_update_flow_new_url_gets_example_existing_url_does_not(self):
        existing = InputURL.objects.create(flow=self.flow, url="https://example.com/old")

        response = self.client.patch(
            f"/api/v2/input_flow/{self.flow.id}/",
            {"urls": [
                {"id": existing.id, "url": "https://example.com/old-renamed"},
                {"url": "https://example.com/new"},
            ]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert existing.scenarios.count() == 0
        new_url = self.flow.urls.get(url="https://example.com/new")
        self.assert_is_example(new_url.scenarios.get(), self.admin)

    # editing and deleting the example

    def create_example(self):
        response = self.client.post(
            f"/api/v2/input_flow/{self.flow.id}/add_url/", {"url": "https://example.com/c"}, format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        return InputScenario.objects.get(url_id=response.data["data"]["id"])

    def test_example_can_be_modified(self):
        scenario = self.create_example()

        response = self.client.patch(
            f"/api/v2/input_scenario/{scenario.id}/",
            {"description": "Validación de CORS", "estimated_time": 30},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        scenario.refresh_from_db()
        assert scenario.description == "Validación de CORS"
        assert scenario.estimated_time == 30

    def test_example_can_be_deleted_by_maintainer_or_above(self):
        scenario = self.create_example()

        response = self.client.delete(f"/api/v2/input_scenario/{scenario.id}/")

        assert response.status_code in {status.HTTP_200_OK, status.HTTP_204_NO_CONTENT}, response.data
        assert not InputScenario.objects.filter(id=scenario.id).exists()

    def test_writer_can_edit_but_not_delete_example(self):
        scenario = self.create_example()
        writer = Dojo_User.objects.create_user(username="flow-writer")
        Product_Member.objects.create(
            user=writer, product=self.flow.engagement.product, role=Role.objects.get(name="Writer"),
        )
        self.client.force_authenticate(user=writer)

        edit = self.client.patch(
            f"/api/v2/input_scenario/{scenario.id}/", {"estimated_time": 45}, format="json",
        )
        delete = self.client.delete(f"/api/v2/input_scenario/{scenario.id}/")

        assert edit.status_code == status.HTTP_200_OK, edit.data
        assert delete.status_code == status.HTTP_403_FORBIDDEN
        assert InputScenario.objects.filter(id=scenario.id).exists()
