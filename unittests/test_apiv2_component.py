from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from dojo.models import Component, Engagement


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

    def test_list_and_detail_include_related_names(self):
        expected = {
            "id": self.component.id,
            "name": self.component.name,
            "version": self.component.version,
            "date": self.component.date.isoformat(),
            "engagement_id": self.engagement.id,
            "engagement_name": self.engagement.name,
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
        self.assertEqual(response.data["product_name"], self.engagement.product.name)
        self.assertEqual(response.data["product_type_name"], self.engagement.product.prod_type.name)
