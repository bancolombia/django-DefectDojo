from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from dojo.models import Dojo_User, Product


class ProductContactsViewSetTestCase(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        self.admin = Dojo_User.objects.get(username="admin")
        token = Token.objects.get(user=self.admin)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.product = Product.objects.get(id=1)
        self.product.technical_contact = self.admin
        self.product.save()
        self.url = reverse("products-get-description-product")

    def test_get_description_product_denies_user_without_product_permission(self):
        unrelated_user = Dojo_User.objects.create_user(username="unrelated-product-user")
        self.client.force_authenticate(user=unrelated_user)

        response = self.client.get(self.url, {"product_id": self.product.id})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_description_product_redacts_contacts_without_admin_permission(self):
        with patch("dojo.api_v2.views.user_has_permission", return_value=False):
            response = self.client.get(self.url, {"product_id": self.product.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contacts = response.data["data"]
        self.assertEqual(
            set(contacts),
            {
                "product_manager",
                "technical_contact",
                "team_manager",
                "product_type_manager",
                "product_type_technical_contact",
                "environment_manager",
                "environment_technical_contact",
            },
        )
        self.assertTrue(all(contact is None for contact in contacts.values()))

    def test_get_description_product_preserves_contacts_for_admin(self):
        response = self.client.get(self.url, {"product_id": self.product.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["technical_contact"]["username"], self.admin.username)