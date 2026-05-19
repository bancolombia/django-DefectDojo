import json
from unittest.mock import patch

from django.urls import reverse

from dojo.models import Engagement, Finding, Product, Test, Test_Type, User

from .dojo_test_case import DojoTestCase


class DisabledInstanceRequestTests(DojoTestCase):

    """Tests for the engagement-level Disabled Instance Request feature."""

    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        super().setUp()
        # Force-login as admin (DojoTestCase.client is a Django test client).
        self.client.force_login(self._get_admin_user())
        # The fixture ships NESSUS Scan but not Tenable Scan; create it on demand.
        self.tenable_test_type, _ = Test_Type.objects.get_or_create(name="Tenable Scan")
        # Build a fresh product + engagement isolated from fixture data.
        self.product = Product.objects.create(
            name="DIR-test-product",
            description="dummy",
            prod_type_id=1,
        )
        self.engagement = Engagement.objects.create(
            name="dir-test-engagement",
            product=self.product,
            target_start="2026-01-01",
            target_end="2026-12-31",
        )
        self.view_url = reverse("view_engagement", args=[self.engagement.id])

    def _get_admin_user(self):
        return User.objects.get(username="admin")

    def _add_tenable_test(self, *, tags=None):
        """Create a Tenable Scan Test attached to self.engagement, optionally tagged."""
        test = Test.objects.create(
            engagement=self.engagement,
            scan_type="Tenable Scan",
            test_type=self.tenable_test_type,
            target_start="2026-01-01",
            target_end="2026-01-02",
        )
        if tags:
            test.tags = tags
            test.save()
        return test

    def _add_finding(self, *, test, tags=None):
        finding = Finding.objects.create(
            test=test,
            title="dir-test-finding",
            severity="High",
            description="dummy",
            mitigation="dummy",
            impact="dummy",
            reporter=self._get_admin_user(),
        )
        if tags:
            finding.tags = tags
            finding.save()
        return finding

    def test_setup_smoke(self):
        """Sanity check that setUp wired everything correctly."""
        self.assertEqual(Test_Type.objects.filter(name="Tenable Scan").count(), 1)
        self.assertIsNotNone(self.engagement.id)

    def test_button_visible_when_engagement_has_tenable_scan_test(self):
        """A Tenable Scan test tagged 'ciclo_escaneo' should reveal the action."""
        self._add_tenable_test(tags=["ciclo_escaneo"])

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disabled Instance Request")

    def test_button_visible_when_engagement_has_finding_with_tenable_tag(self):
        """A Finding tag containing 'tenable' reveals the action even when the parent test is not Tenable."""
        nessus_type, _ = Test_Type.objects.get_or_create(name="NESSUS Scan")
        non_tenable_test = Test.objects.create(
            engagement=self.engagement,
            scan_type="NESSUS Scan",
            test_type=nessus_type,
            target_start="2026-01-01",
            target_end="2026-01-02",
        )
        self._add_finding(test=non_tenable_test, tags=["Tenable_io_finding"])

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disabled Instance Request")

    def test_button_hidden_when_no_tenable_signal(self):
        """Engagement with non-Tenable test and no tenable-tagged findings should hide the action."""
        nessus_type, _ = Test_Type.objects.get_or_create(name="NESSUS Scan")
        Test.objects.create(
            engagement=self.engagement,
            scan_type="NESSUS Scan",
            test_type=nessus_type,
            target_start="2026-01-01",
            target_end="2026-01-02",
        )

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Disabled Instance Request")

    def test_button_hidden_when_only_tenable_test_is_transferred(self):
        """A Tenable Scan test tagged 'transferred' (mixed-case) must be excluded from OR-A."""
        self._add_tenable_test(tags=["ciclo_escaneo", "Transferred"])

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Disabled Instance Request")

    def test_endpoint_requires_login(self):
        """Unauthenticated GET to the disabled_instance_request endpoint should redirect to login."""
        from django.conf import settings

        self.client.logout()
        url = reverse("disabled_instance_request", args=[self.engagement.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(settings.LOGIN_URL, response.url)

    @patch("dojo.engagement.views.Token")
    @patch("dojo.engagement.views.User")
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_success_on_external_200(self, mock_requests, mock_user_cls, mock_token_cls):
        """When the external API returns 200, the view returns success JSON and posts the engagement name."""
        # OPERATIVE_USER ("operative") is not in the fixture; mock both User and Token lookups.
        mock_user_cls.objects.get.return_value = self._get_admin_user()
        mock_token_cls.objects.get.return_value.key = "fake-operative-token"
        mock_requests.post.return_value.status_code = 200

        url = reverse("disabled_instance_request", args=[self.engagement.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body["success"])
        self.assertIn("successfully", body["message"])
        # Verify the external API was called with engagement.name as dnsname.
        mock_requests.post.assert_called_once()
        called_url = mock_requests.post.call_args.args[0]
        self.assertIn("disabledInstanceRequest", called_url)
        call_kwargs = mock_requests.post.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"dnsname": self.engagement.name})
        self.assertIn("Authorization", call_kwargs["headers"])
        # Bound external call — guard against accidental removal of the timeout.
        self.assertEqual(call_kwargs["timeout"], (5, 10))

    @patch("dojo.engagement.views.Token")
    @patch("dojo.engagement.views.User")
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_500_on_external_failure(self, mock_requests, mock_user_cls, mock_token_cls):
        """When the external API returns non-200, the view returns 500 JSON with success=false."""
        mock_user_cls.objects.get.return_value = self._get_admin_user()
        mock_token_cls.objects.get.return_value.key = "fake-operative-token"
        mock_requests.post.return_value.status_code = 503

        url = reverse("disabled_instance_request", args=[self.engagement.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        body = json.loads(response.content)
        self.assertFalse(body["success"])
        self.assertIn("error", body)

    @patch("dojo.engagement.views.Token")
    @patch("dojo.engagement.views.User")
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_500_on_network_exception(self, mock_requests, mock_user_cls, mock_token_cls):
        """When requests.post raises (e.g. network error), the view returns 500 JSON with success=false."""
        mock_user_cls.objects.get.return_value = self._get_admin_user()
        mock_token_cls.objects.get.return_value.key = "fake-operative-token"
        mock_requests.post.side_effect = Exception("simulated network failure")

        url = reverse("disabled_instance_request", args=[self.engagement.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        body = json.loads(response.content)
        self.assertFalse(body["success"])
        self.assertIn("error", body)
