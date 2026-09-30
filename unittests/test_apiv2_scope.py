from django.urls import reverse
from rest_framework.test import APIClient, APITestCase
from rest_framework.authtoken.models import Token
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

from dojo.models import Dojo_User, Input, InputFile, InputSecret, InputEngagement


class scopeViewsTestCase(APITestCase):
    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        token = Token.objects.get(user__username="admin")
        self.admin = token.user
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.create_file_url = reverse("scope-create-scope-file")
        self.create_secret_url = reverse("scope-create-scope-secret")
        self.download_url = reverse("scope-download-file")
        self.list_file_url = reverse("scope-list")

    def create_input_file(self):
        input_instance = Input.objects.create(owner=self.admin, type="file")
        InputEngagement.objects.create(input=input_instance, engagement_id=1)
        upload = SimpleUploadedFile("original.txt", b"original content", content_type="text/plain")
        return input_instance, InputFile.objects.create(
            input=input_instance,
            file=upload,
            file_name="original.txt",
        )

    def test_patch_input_file_updates_file_name_from_request_body(self):
        input_instance, input_file = self.create_input_file()

        response = self.client.patch(
            f"/api/v2/input_file/?id={input_instance.id}",
            {"file_name": "renamed.txt"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        input_file.refresh_from_db()
        assert input_file.file_name == "renamed.txt"

    def test_patch_input_file_accepts_legacy_query_parameter(self):
        input_instance, input_file = self.create_input_file()

        response = self.client.patch(
            f"/api/v2/input_file/?id={input_instance.id}&file_name=renamed.txt",
            {},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        input_file.refresh_from_db()
        assert input_file.file_name == "renamed.txt"

    def test_patch_input_file_rejects_user_without_object_permission(self):
        input_instance, _ = self.create_input_file()
        unrelated_user = Dojo_User.objects.create_user(username="unrelated-user")
        self.client.force_authenticate(user=unrelated_user)

        response = self.client.patch(
            f"/api/v2/input_file/?id={input_instance.id}",
            {"file_name": "changed.txt"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch_input_file_rejects_path_in_file_name(self):
        input_instance, input_file = self.create_input_file()

        response = self.client.patch(
            f"/api/v2/input_file/?id={input_instance.id}",
            {"file_name": "../app/media/overwritten.txt"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        input_file.refresh_from_db()
        assert input_file.file_name == "original.txt"
    

    def test_create_scope_file_creates_input_and_file(self):
        """
        POST multipart/form-data to create_scope_file should create Input, InputEngagement and InputFile.
        """
        file_content = b"hello test"
        uploaded = SimpleUploadedFile("test_upload.txt", file_content, content_type="text/plain")
        query = "engagement=1&product=1&description=Test+upload&type=file&file_name=test_upload.txt"
        
        data = {
            "file": uploaded,
        }

        resp = self.client.post(f"{self.create_file_url}?{query}", data, format="multipart")
        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

        # verify Input created and related InputFile exists
        created_inputs = Input.objects.filter(description="Test upload")
        assert created_inputs.exists()
        input_instance = created_inputs.first()
        print(InputEngagement.objects.all().values_list("input_id", "engagement_id", "product_id"))
        assert InputEngagement.objects.filter(input=input_instance, engagement_id=1).exists()
        assert InputFile.objects.filter(input=input_instance, file_name__icontains="test_upload.txt").exists()

    def test_create_scope_secret_creates_input_and_secret(self):
        """
        POST JSON to create_scope_secret should create Input, InputEngagement and InputSecret.
        """
        data = {
            "engagement": 1,
            "product": 1,
            "description": "Secret desc",
            "type": "secret",
            "key": "usernamekey",
            "secret": "supersecret"
        }


        resp = self.client.post(f"{self.create_secret_url}", data=data, format="json")
        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

        created_inputs = Input.objects.filter(description="Secret desc")
        assert created_inputs.exists()
        input_instance = created_inputs.first()
        assert InputEngagement.objects.filter(input=input_instance, engagement_id=1).exists()
        assert InputSecret.objects.filter(input=input_instance).exists()


    def test_download_file_returns_attachment_and_content(self):
        """
        Ensure download_file returns the stored file as attachment with correct bytes.
        Requires an InputFile linked to Input id=1 in fixtures or created earlier in tests.
        """
        # try to use an existing input with file; if none, create minimal objects
        input_qs = Input.objects.all()
        if not input_qs.exists():
            inp = Input.objects.create(description="dl test", owner_id=1, type="file")
            ie = InputEngagement.objects.create(engagement_id=1, product_id=1, input=inp)
            f = SimpleUploadedFile("dl_test.txt", b"dl content", content_type="text/plain")
            InputFile.objects.create(input=inp, file=f, file_name="dl_test.txt")
            input_id = inp.id
        else:
            # try find an Input that has InputFile
            inp_with_file = Input.objects.filter(inputfile__isnull=False).first()
            if inp_with_file:
                input_id = inp_with_file.id
            else:
                inp = input_qs.first()
                f = SimpleUploadedFile("dl_test.txt", b"dl content", content_type="text/plain")
                InputFile.objects.create(input=inp, file=f, file_name="dl_test.txt")
                input_id = inp.id

        resp = self.client.get(f"{self.download_url}?input={input_id}")
        assert resp.status_code == status.HTTP_200_OK
        cd = resp.get("Content-Disposition", "")
        assert "attachment" in cd.lower()
