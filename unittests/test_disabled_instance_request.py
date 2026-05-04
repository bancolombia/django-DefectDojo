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
