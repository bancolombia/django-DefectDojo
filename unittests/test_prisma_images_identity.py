import base64
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from dojo.finding.prisma_images_identity import EngineImageClient, EngineLookupError, prepare_finding_identity
from dojo.models import Engagement, Finding, User
from dojo.models import Test as ScanTest


class PrismaIdentityTests(SimpleTestCase):
    suffix = "CVE-1,high,openssl,1,9.00,fixed"
    image = "registry/app:v1"

    def finding(self):
        identity = "registry/app@sha256:old," + self.suffix
        return SimpleNamespace(
            unique_id_from_tool=base64.b64encode(identity.encode()).decode(),
            impact="Registry: registry\nRepository: app\nImage ID: sha256:old",
            description="<p><strong>Tag:</strong> v1</p><p><strong>Cloud Id:</strong> sha256:old</p>"
                        "<p><strong>Custom Id:</strong> " + identity + "</p><p>Keep this note</p>",
        )

    def test_orders_pairs_and_preserves_original_vulnerability_values(self):
        result = prepare_finding_identity(self.finding(), [self.image], {
            self.image: [("deploy-2", "container-2"), ("deploy-1", "container-1"), ("deploy-1", "container-1")],
        })
        self.assertEqual("registry/app@deploy-1,container-1,deploy-2,container-2," + self.suffix,
                         base64.b64decode(result["unique_id_from_tool"]).decode())
        self.assertIn("Deployment:</strong> deploy-1,deploy-2", result["description"])
        self.assertIn("Container Name:</strong> container-1,container-2", result["description"])
        self.assertIn("Keep this note", result["description"])

    def test_no_runtime_images_uses_two_empty_fields_like_extractor(self):
        result = prepare_finding_identity(self.finding(), [], {})
        self.assertEqual("registry/app@,," + self.suffix, base64.b64decode(result["unique_id_from_tool"]).decode())
        self.assertEqual(0, result["deployment_count"])

    def test_runtime_image_without_deployments_uses_empty_fields(self):
        result = prepare_finding_identity(self.finding(), [self.image], {})
        self.assertEqual("registry/app@,," + self.suffix, base64.b64decode(result["unique_id_from_tool"]).decode())

    def test_repeated_migration_is_idempotent(self):
        finding = self.finding()
        first = prepare_finding_identity(finding, [self.image], {self.image: [("deploy-1", "container-1")]})
        finding.unique_id_from_tool = first["unique_id_from_tool"]
        finding.description = first["description"]
        second = prepare_finding_identity(finding, [self.image], {self.image: [("deploy-1", "container-1")]})
        self.assertEqual(first, second)

    def test_old_tag_can_use_unambiguous_runtime_deployments(self):
        image = "registry/app:v2"
        result = prepare_finding_identity(self.finding(), [image], {image: [("deploy-1", "container-1")]})
        self.assertEqual(1, result["deployment_count"])

    def test_ambiguous_runtime_tags_are_not_migrated(self):
        with self.assertRaisesRegex(ValueError, "different deployments"):
            prepare_finding_identity(self.finding(), ["registry/app:v2", "registry/app:v3"], {
                "registry/app:v2": [("deploy-1", "container-1")],
                "registry/app:v3": [("deploy-2", "container-2")],
            })

    def test_comma_in_package_and_original_cvss_are_preserved(self):
        finding = self.finding()
        suffix = "CVE-1,high,lib-one,lib-two,1,9.00,fixed"
        finding.unique_id_from_tool = base64.b64encode(("registry/app@sha256:old," + suffix).encode()).decode()
        result = prepare_finding_identity(finding, [], {})
        self.assertEqual("registry/app@,," + suffix, base64.b64decode(result["unique_id_from_tool"]).decode())


@override_settings(PROVIDER_CORE_ENGINE="https://search.example/")
class EngineImageClientTests(SimpleTestCase):
    @patch("dojo.finding.prisma_images_identity.requests.Session")
    def test_runtime_search_uses_engagement_and_image_key(self, session_class):
        response = session_class.return_value.request.return_value
        response.status_code = 200
        response.json.return_value = {"images": ["registry/app:v1"]}
        client = EngineImageClient()
        self.assertEqual(["registry/app:v1"], client.get_runtime("app"))
        session_class.return_value.request.assert_called_once_with(
            "GET", "https://search.example/engine-backend/search/getImagesRuntime",
            timeout=(5, 60), allow_redirects=False, params={"searchKey": "image", "searchValue": "app"},
        )

    @patch("dojo.finding.prisma_images_identity.requests.Session")
    def test_deployments_are_queried_in_batches_and_empty_list_skips_call(self, session_class):
        response = session_class.return_value.request.return_value
        response.status_code = 200
        response.json.return_value = {"deployments": []}
        client = EngineImageClient()
        self.assertEqual({}, client.get_deployments([]))
        session_class.return_value.request.assert_not_called()
        images = [f"registry/app:v{index}" for index in range(501)]
        self.assertEqual({}, client.get_deployments(images))
        calls = session_class.return_value.request.call_args_list
        self.assertEqual([500, 1], [len(call.kwargs["json"]["images"]) for call in calls])

    @patch("dojo.finding.prisma_images_identity.requests.Session")
    def test_network_failure_is_not_interpreted_as_empty_runtime(self, session_class):
        session_class.return_value.request.side_effect = requests.Timeout()
        with self.assertRaises(EngineLookupError):
            EngineImageClient().get_runtime("app")


@override_settings(PROVIDER_CORE_ENGINE="https://search.example/",
                   CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class PrismaIdentityMigrationApiTests(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        self.client.force_authenticate(User.objects.get(username="admin"))
        self.url = reverse("finding-bulk-migrate-prisma-ids")
        self.finding = Finding.objects.order_by("pk").first()
        Finding.objects.exclude(pk=self.finding.pk).update(active=False)
        ScanTest.objects.filter(pk=self.finding.test_id).update(title="ciclo_escaneo")
        self.engagement = self.finding.test.engagement
        Engagement.objects.filter(pk=self.engagement.pk).update(name="app", description="ITEM: IMAGES\nPROVIDER: PRISMA")
        source = PrismaIdentityTests().finding()
        Finding.objects.filter(pk=self.finding.pk).update(
            active=True, is_mitigated=False, description=source.description,
            impact=source.impact, unique_id_from_tool=source.unique_id_from_tool,
        )
        self.finding.refresh_from_db()
        self.finding.tags = ["prisma", "images"]
        self.finding.save()
        self.old_id = self.finding.unique_id_from_tool

    def configure_client(self, client_class, images=None):
        client_class.return_value.get_runtime.return_value = ["registry/app:v1"] if images is None else images
        client_class.return_value.get_deployments.return_value = {"registry/app:v1": [("deploy-1", "container-1")]}

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_default_dry_run_discovers_engagement_without_writing(self, client_class):
        self.configure_client(client_class)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(202, response.status_code, response.data)
        self.assertEqual("queued", response.data["status"])
        self.assertTrue(response.data["dry_run"])
        self.finding.refresh_from_db()
        self.assertEqual(self.old_id, self.finding.unique_id_from_tool)
        client_class.return_value.get_runtime.assert_called_once_with("app")

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_migrates_active_findings_and_is_idempotent(self, client_class):
        self.configure_client(client_class)
        payload = {"dry_run": False, "engagement_ids": [self.engagement.pk]}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(202, response.status_code, response.data)
        self.finding.refresh_from_db()
        self.assertEqual("registry/app@deploy-1,container-1," + PrismaIdentityTests.suffix,
                         base64.b64decode(self.finding.unique_id_from_tool).decode())
        self.assertIn("Deployment:</strong> deploy-1", self.finding.description)
        self.assertIn("Container Name:</strong> container-1", self.finding.description)
        migrated_id = self.finding.unique_id_from_tool
        second = self.client.post(self.url, payload, format="json")
        self.assertEqual(202, second.status_code, second.data)
        self.finding.refresh_from_db()
        self.assertEqual(migrated_id, self.finding.unique_id_from_tool)

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_no_runtime_images_migrates_to_empty_deployment_fields(self, client_class):
        self.configure_client(client_class, images=[])
        client_class.return_value.get_deployments.return_value = {}
        response = self.client.post(self.url, {"dry_run": False}, format="json")
        self.assertEqual(202, response.status_code, response.data)
        self.finding.refresh_from_db()
        self.assertEqual("registry/app@,," + PrismaIdentityTests.suffix,
                         base64.b64decode(self.finding.unique_id_from_tool).decode())
        client_class.return_value.get_deployments.assert_called_once_with([])

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_lookup_error_does_not_change_finding(self, client_class):
        client_class.return_value.get_runtime.side_effect = EngineLookupError("Unavailable")
        response = self.client.post(self.url, {"dry_run": False}, format="json")
        self.assertEqual(202, response.status_code)
        client_class.return_value.get_runtime.assert_called_once_with("app")
        self.finding.refresh_from_db()
        self.assertEqual(self.old_id, self.finding.unique_id_from_tool)

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_wrong_item_test_tag_or_inactive_finding_are_excluded(self, client_class):
        for field, value in [("active", False), ("is_mitigated", True)]:
            with self.subTest(field=field):
                Finding.objects.filter(pk=self.finding.pk).update(**{field: value})
                response = self.client.post(self.url, {}, format="json")
                self.assertEqual(202, response.status_code)
                Finding.objects.filter(pk=self.finding.pk).update(active=True, is_mitigated=False)
        Engagement.objects.filter(pk=self.engagement.pk).update(description="ITEM: HOSTS")
        self.assertEqual(202, self.client.post(self.url, {}, format="json").status_code)
        Engagement.objects.filter(pk=self.engagement.pk).update(description="ITEM: ECR")
        ScanTest.objects.filter(pk=self.finding.test_id).update(title="other scan")
        self.assertEqual(202, self.client.post(self.url, {}, format="json").status_code)
        ScanTest.objects.filter(pk=self.finding.test_id).update(title="ciclo escaneo")
        self.finding.tags = ["prisma"]
        self.finding.save()
        self.assertEqual(202, self.client.post(self.url, {}, format="json").status_code)
        client_class.assert_not_called()

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_user_without_edit_permission_cannot_migrate(self, client_class):
        user = User.objects.create(username="migration-without-access", is_active=True)
        self.client.force_authenticate(user)
        response = self.client.post(self.url, {"dry_run": False}, format="json")
        self.assertEqual(202, response.status_code, response.data)
        client_class.assert_not_called()

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_accepts_ecr_item_and_scan_title_with_spaces(self, client_class):
        self.configure_client(client_class)
        Engagement.objects.filter(pk=self.engagement.pk).update(description="ITEM: ECR\nPROVIDER: PRISMA")
        ScanTest.objects.filter(pk=self.finding.test_id).update(title="Ciclo Escaneo")
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(202, response.status_code, response.data)
        client_class.return_value.get_runtime.assert_called_once_with("app")

    @patch("dojo.finding.prisma_images_identity.EngineImageClient")
    def test_processes_every_engagement_in_batches_without_reprocessing(self, client_class):
        self.configure_client(client_class)
        other = Finding.objects.exclude(test__engagement_id=self.engagement.pk).order_by("pk").first()
        self.assertIsNotNone(other)
        ScanTest.objects.filter(pk=other.test_id).update(title="ciclo_escaneo")
        Engagement.objects.filter(pk=other.test.engagement_id).update(description="ITEM: ECR")
        Finding.objects.filter(pk=other.pk).update(
            active=True, is_mitigated=False, unique_id_from_tool=self.old_id,
            description=self.finding.description, impact=self.finding.impact,
        )
        other.refresh_from_db()
        other.tags = ["prisma", "images"]
        other.save()
        response = self.client.post(self.url, {"limit": 1}, format="json")
        self.assertEqual(202, response.status_code, response.data)
        processed = sorted(call.args[0] for call in client_class.return_value.get_runtime.call_args_list)
        self.engagement.refresh_from_db()
        self.assertEqual(sorted([self.engagement.name, other.test.engagement.name]), processed)

    def test_requires_authentication_and_valid_limits(self):
        response = self.client.post(self.url, {"limit": 51}, format="json")
        self.assertEqual(400, response.status_code)
        self.assertIn(APIClient().post(self.url, {}, format="json").status_code, [401, 403])
