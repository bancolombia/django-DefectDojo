from crum import impersonate
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

import dojo.jira_link.helper  # noqa: F401  # must load before dojo.forms (circular import)
from dojo.api_v2.scope.models import InputFlow
from dojo.forms import AddFindingForm, FindingForm
from dojo.models import Dojo_User, Engagement, Finding, Product_Member, Role, Test


class FindingInputFlowsTestCase(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        token = Token.objects.get(user__username="admin")
        self.admin = token.user
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        # finding 2 -> test 3 -> engagement 1 -> product 2
        self.finding = Finding.objects.get(id=2)
        self.engagement = self.finding.test.engagement
        self.flow_a = InputFlow.objects.create(flowName="flow a", engagement=self.engagement)
        self.flow_b = InputFlow.objects.create(flowName="flow b", engagement=self.engagement)
        # same product, different engagement
        self.flow_other_engagement = InputFlow.objects.create(flowName="other engagement", engagement_id=3)
        # different product (engagement 2 -> product 1)
        self.flow_other_product = InputFlow.objects.create(flowName="other product", engagement_id=2)

        self.url = f"/api/v2/findings/{self.finding.id}/"

    def login_as_product_writer(self):
        user = Dojo_User.objects.create_user(username="flow-writer")
        Product_Member.objects.create(
            user=user, product=self.engagement.product, role=Role.objects.get(name="Writer"),
        )
        self.client.force_authenticate(user=user)
        return user

    # API

    def test_get_finding_includes_input_flows(self):
        self.finding.Input_flows.set([self.flow_a, self.flow_b])

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert sorted(response.data["input_flows"], key=lambda f: f["id"]) == [
            {"id": self.flow_a.id, "flowName": "flow a"},
            {"id": self.flow_b.id, "flowName": "flow b"},
        ]

    def test_patch_sets_multiple_input_flows(self):
        response = self.client.patch(
            self.url, {"input_flows_ids": [self.flow_a.id, self.flow_b.id]}, format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert set(self.finding.Input_flows.values_list("id", flat=True)) == {self.flow_a.id, self.flow_b.id}

    def test_patch_without_input_flows_keeps_existing(self):
        self.finding.Input_flows.set([self.flow_a, self.flow_b])

        response = self.client.patch(self.url, {"title": "new title"}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert self.finding.Input_flows.count() == 2

    def test_patch_with_empty_list_clears_input_flows(self):
        self.finding.Input_flows.set([self.flow_a, self.flow_b])

        response = self.client.patch(self.url, {"input_flows_ids": []}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert self.finding.Input_flows.count() == 0

    def test_patch_rejects_flow_from_other_engagement(self):
        response = self.client.patch(
            self.url, {"input_flows_ids": [self.flow_a.id, self.flow_other_engagement.id]}, format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "input_flows_ids" in response.data
        assert self.finding.Input_flows.count() == 0

    def test_patch_rejects_flow_user_cannot_view(self):
        self.login_as_product_writer()

        response = self.client.patch(
            self.url, {"input_flows_ids": [self.flow_other_product.id]}, format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not exist" in str(response.data["input_flows_ids"])
        assert self.finding.Input_flows.count() == 0

    def test_patch_allows_writer_on_own_product(self):
        self.login_as_product_writer()

        response = self.client.patch(
            self.url, {"input_flows_ids": [self.flow_a.id]}, format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert list(self.finding.Input_flows.values_list("id", flat=True)) == [self.flow_a.id]

    def test_create_finding_with_multiple_input_flows(self):
        payload = {
            "test": self.finding.test.id,
            "found_by": [],
            "title": "finding with flows",
            "date": "2026-10-05",
            "severity": "High",
            "description": "description",
            "active": True,
            "verified": False,
            "numerical_severity": "S1",
            "input_flows_ids": [self.flow_a.id, self.flow_b.id],
        }

        response = self.client.post("/api/v2/findings/", payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        finding = Finding.objects.get(id=response.data["id"])
        assert set(finding.Input_flows.values_list("id", flat=True)) == {self.flow_a.id, self.flow_b.id}
        assert len(response.data["input_flows"]) == 2

    def test_create_finding_rejects_flow_from_other_engagement(self):
        payload = {
            "test": self.finding.test.id,
            "found_by": [],
            "title": "finding with bad flow",
            "date": "2026-10-05",
            "severity": "High",
            "description": "description",
            "active": True,
            "verified": False,
            "numerical_severity": "S1",
            "input_flows_ids": [self.flow_other_engagement.id],
        }

        response = self.client.post("/api/v2/findings/", payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Finding.objects.filter(title="finding with bad flow").exists()

    # Forms

    def test_add_finding_form_offers_only_engagement_flows(self):
        form = AddFindingForm(req_resp=None, product=self.engagement.product, engagement=self.engagement)

        assert set(form.fields["flows"].queryset) == {self.flow_a, self.flow_b}

    def test_add_finding_form_accepts_multiple_flows(self):
        form = AddFindingForm(
            {"flows": [self.flow_a.id, self.flow_b.id]},
            req_resp=None, product=self.engagement.product, engagement=self.engagement,
        )
        form.is_valid()

        assert "flows" not in form.errors
        assert set(form.cleaned_data["flows"]) == {self.flow_a, self.flow_b}

    def test_add_finding_form_rejects_flow_from_other_engagement(self):
        form = AddFindingForm(
            {"flows": [self.flow_other_engagement.id]},
            req_resp=None, product=self.engagement.product, engagement=self.engagement,
        )
        form.is_valid()

        assert "flows" in form.errors

    def test_finding_form_preloads_all_flows(self):
        self.finding.Input_flows.set([self.flow_a, self.flow_b])

        with impersonate(self.admin):
            form = FindingForm(instance=self.finding)

        assert set(form.fields["flows"].initial) == {self.flow_a, self.flow_b}
        assert set(form.fields["flows"].queryset) == {self.flow_a, self.flow_b}

    def test_engagement_and_test_fixture_assumptions(self):
        # guards the ids the other tests rely on
        assert Test.objects.get(id=3).engagement_id == 1
        assert Engagement.objects.get(id=3).product_id == self.engagement.product_id
        assert Engagement.objects.get(id=2).product_id != self.engagement.product_id
