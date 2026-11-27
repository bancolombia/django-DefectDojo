from unittest.mock import patch

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from dojo.models import Component, Engagement, Product


class ComponentApiTest(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        token = Token.objects.get(user__username="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.engagement = Engagement.objects.select_related("product__prod_type").first()
        self.component = Component.objects.create(
            name="test-component",
            version="1.0",
            engagement=self.engagement,
        )

    def create_engagement(self, product):
        with patch("dojo.engagement.signals.create_notification"):
            return Engagement.objects.create(
                name="other-engagement",
                product=product,
                target_start=self.engagement.target_start,
                target_end=self.engagement.target_end,
            )

    def test_list_and_detail_include_related_names(self):
        expected = {
            "id": self.component.id,
            "name": self.component.name,
            "version": self.component.version,
            "date": self.component.date.isoformat(),
            "engagement_id": self.engagement.id,
            "engagement_name": self.engagement.name,
            "product_id": self.engagement.product_id,
            "product_name": self.engagement.product.name,
            "product_type_name": self.engagement.product.prod_type.name,
        }
        response = self.client.get(reverse("components-list"), {"engagement_id": self.engagement.id})
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected, response.data["results"])

        response = self.client.get(reverse("components-detail", args=[self.component.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, expected)

    def test_null_engagement_name_is_returned(self):
        # Bypass the pre-save signal that replaces empty names with the start date.
        Engagement.objects.filter(pk=self.engagement.pk).update(name=None)
        response = self.client.get(reverse("components-detail", args=[self.component.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["engagement_name"])

    def test_create_does_not_require_related_names(self):
        response = self.client.post(reverse("components-list"), {
            "name": "another-component",
            "version": "2.0",
            "engagement_id": self.engagement.id,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["engagement_name"], self.engagement.name)
        self.assertEqual(response.data["product_id"], self.engagement.product_id)
        self.assertEqual(response.data["product_name"], self.engagement.product.name)
        self.assertEqual(response.data["product_type_name"], self.engagement.product.prod_type.name)

    def test_update_preserves_identity_and_updates_date(self):
        response = self.client.put(reverse("components-detail", args=[self.component.id]), {
            "name": self.component.name,
            "version": self.component.version,
            "engagement_id": self.engagement.id,
            "date": "2026-01-02",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.component.refresh_from_db()
        self.assertEqual(self.component.date.isoformat(), "2026-01-02")
        self.assertEqual(response.data["product_id"], self.engagement.product_id)

    def test_partial_update_rejects_duplicate_component(self):
        Component.objects.create(name="existing", version=self.component.version, engagement=self.engagement)
        response = self.client.patch(reverse("components-detail", args=[self.component.id]), {
            "name": "existing",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.component.refresh_from_db()
        self.assertEqual(self.component.name, "test-component")

    def test_update_engagement_uses_new_product(self):
        product = Product.objects.exclude(pk=self.engagement.product_id).first()
        self.assertIsNotNone(product)
        engagement = self.create_engagement(product)
        response = self.client.patch(reverse("components-detail", args=[self.component.id]), {
            "engagement_id": engagement.id,
            "product_id": self.engagement.product_id,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.component.refresh_from_db()
        self.assertEqual(self.component.engagement_id, engagement.id)
        self.assertEqual(response.data["product_id"], product.id)
        self.assertEqual(response.data["product_name"], product.name)

    def test_update_rejects_unknown_engagement(self):
        response = self.client.patch(reverse("components-detail", args=[self.component.id]), {
            "engagement_id": 999999999,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_update_rejects_unauthorized_destination(self):
        engagement = self.create_engagement(self.engagement.product)
        with patch("dojo.api_v2.serializers.user_has_permission", return_value=False):
            response = self.client.patch(reverse("components-detail", args=[self.component.id]), {
                "engagement_id": engagement.id,
            }, format="json")
        self.assertEqual(response.status_code, 403)
        self.component.refresh_from_db()
        self.assertEqual(self.component.engagement_id, self.engagement.id)

    def test_filter_components_by_product_and_engagement(self):
        product = Product.objects.exclude(pk=self.engagement.product_id).first()
        self.assertIsNotNone(product)
        other_engagement = self.create_engagement(product)
        other = Component.objects.create(name="other", version="1", engagement=other_engagement)
        url = reverse("components-filter-components")

        for filters, expected in (
            ({"product_id": self.engagement.product_id}, self.component),
            ({"engagement_id": other_engagement.id}, other),
            ({"product_id": product.id, "engagement_id": other_engagement.id}, other),
        ):
            with self.subTest(filters=filters):
                response = self.client.get(url, filters)
                self.assertEqual(response.status_code, 200)
                ids = {item["id"] for item in response.data["results"]}
                self.assertIn(expected.id, ids)
                self.assertNotIn((other if expected == self.component else self.component).id, ids)

        response = self.client.get(url, {
            "product_id": self.engagement.product_id,
            "engagement_id": other_engagement.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_filter_components_validates_ids_and_authorization(self):
        url = reverse("components-filter-components")
        for filters in ({"product_id": "invalid"}, {"engagement_id": "invalid"}, {"product_id": 0}):
            with self.subTest(filters=filters):
                self.assertEqual(self.client.get(url, filters).status_code, 400)

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.component.id, {item["id"] for item in response.data["results"]})

        with patch("dojo.api_v2.views.get_authorized_engagements", return_value=Engagement.objects.none()):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

        self.client.credentials()
        self.assertIn(self.client.get(url).status_code, (401, 403))
