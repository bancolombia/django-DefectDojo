import logging
from django.db import transaction
from rest_framework import serializers
from dojo.models import Engagement, Product, Dojo_User
from dojo.api_v2.scope.models import InputSecret, InputFile, Input, InputEngagement, InputScenario, InputFlow, InputURL
from dojo.utils import dojo_crypto_encrypt, prepare_for_view
from drf_spectacular.utils import extend_schema_field
import dojo.authorization.helper as authorization_helper


logger = logging.getLogger(__name__)


# ...existing code...
class InputSecretSerializer(serializers.ModelSerializer):

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "input": instance.input.id,
            "key": prepare_for_view(instance.key),
            "secret": prepare_for_view(instance.secret),
            "status": instance.status,
        }
    
    def update(self, instance, validated_data):
        instance.key = dojo_crypto_encrypt(validated_data.get('key', instance.key))
        instance.secret = dojo_crypto_encrypt(validated_data.get('secret', instance.secret))
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        return instance
        
    class Meta:
        model = InputSecret
        fields = [
            "input",
            "key",
            "secret",
            "status"
        ]
    

class InputFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = InputFile
        fields = [
            "input",
            "file",
            "file_name"
        ]
    
    def update(self, instance, validated_data):
        request = validated_data.pop("request", None)
        instance.file = request.data.get('file', instance.file) if request else instance.file 
        instance.file_name = validated_data.get('file_name', instance.file_name)
        instance.save()
        return instance

class ScopeFileSerializers(serializers.Serializer):
    CHOICES = (
        ("secret", "Secret"),
        ("file", "File"),
    )
    engagement = serializers.PrimaryKeyRelatedField(queryset=Engagement.objects.all(), required=False, allow_null=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    description = serializers.CharField()
    url = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    file = serializers.FileField(required=False, allow_null=True)
    file_name = serializers.CharField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=CHOICES, required=True)
    
    def create(self, validated_data):
        request = validated_data.pop("request", None)
        owner = request.user if request else None 

        with transaction.atomic():
            input_instance = Input.objects.create(
                description=validated_data['description'],
                owner=owner,
                type=validated_data['type']
            )
            input_engagement_instance = InputEngagement.objects.create(
                engagement=validated_data.get('engagement', None),
                product=validated_data.get('product', None),
                input=input_instance
            )
            if file := request.data.get('file'):
                InputFile.objects.create(
                    input=input_instance,
                    file=file,
                    file_name=validated_data.get('file_name', file.name)
                )
        return input_engagement_instance


class ScopeSecretSerializers(serializers.Serializer):
    CHOICES = (
        ("secret", "Secret"),
        ("file", "File"),
        ("desc", "Desc"),
    )
    engagement = serializers.PrimaryKeyRelatedField(queryset=Engagement.objects.all(), required=False, allow_null=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    description = serializers.CharField(required=False)
    type = serializers.ChoiceField(choices=CHOICES, required=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=Dojo_User.objects.all(), required=False)
    url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    key = serializers.CharField(required=False)
    secret = serializers.CharField(required=False)
    status = serializers.BooleanField(default=True, required=False)
    
    def create(self, validated_data):
        owner = validated_data.pop("owner", None)
        with transaction.atomic():
            input_instance = Input.objects.create(
                description=validated_data.get('description', ""),
                owner=owner,
                url=validated_data.get("url", None),
                type=validated_data["type"]
            )
            input_engagement_instance = InputEngagement.objects.create(
                engagement=validated_data.get("engagement"),
                product=validated_data.get("product"),
                input=input_instance
            )
            InputSecret.objects.create(
                input=input_instance,
                key=dojo_crypto_encrypt(validated_data.get("key", None)),
                secret=dojo_crypto_encrypt(validated_data.get("secret", None)),
                status=validated_data.get("status")
            )
        return input_engagement_instance 

class InputBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Input
        fields = ["id", "description", "type", "owner", "url", "created", "updated"]

class InputEngagementSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    engagement = serializers.IntegerField(source="engagement_id")
    product = serializers.IntegerField(source="product_id")
    input = serializers.SerializerMethodField()

    class Meta:
        model = InputEngagement
        fields = ["id", "engagement", "product", "input"]
    
    def get_input(self, obj):
        input_obj = getattr(obj, "input", None)
        if not input_obj:
            return None

        try:
            serializer = None
            if hasattr(input_obj, "inputsecret"):
                secret = InputSecret.objects.get(input=input_obj)
                serializer =  InputSecretSerializer(secret).data
            else:
                f = InputFile.objects.get(input=input_obj)
                serializer =  InputFileSerializer(f).data
            return serializer
        except Exception as e:
            logger.error(f"Scope {str(e)}, input_id = {input_obj.id}")
            return InputBasicSerializer(input_obj).data

class InputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    description = serializers.CharField(max_length=255, required=False)
    type = serializers.CharField(required=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=Dojo_User.objects.all(), required=False)
    url = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    input_engagement = InputEngagementSerializer(source="inputengagement_set", many=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    permissions = serializers.SerializerMethodField(read_only=True, allow_null=True)
    
    def update(self, instance, validated_data):
        engagements = validated_data.pop('inputengagement_set', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        self.update_input_engagement(instance, engagements)
                    
        instance.save()
        return instance
    
     
    def update_input_engagement(self, instance, input_engagements):
        if input_engagements:
            for input_engagement in input_engagements:
                id_input_eng = input_engagement.get("id")
                InputEngagement.objects.filter(id=id_input_eng).update(
                    engagement_id=input_engagement["engagement_id"]) 

    class Meta:
        model = Input 
        fields = [
            "id",
            "description",
            "type",
            "owner",
            "input",
            "url",
            "created",
            "updated"]


    @extend_schema_field(serializers.ListField())
    def get_permissions(self, obj):
        return authorization_helper.get_permissions(obj)

class InputScenarioSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = InputScenario
        fields = [
            "id",
            "estimated_time",
            "designed_by",
            "description",
            "verified",

        ]
        read_only_fields = ["id"]

    def validate_estimated_time(self, value):
        if value is None:
            raise serializers.ValidationError("estimated_time is required.")
        if value <= 0:
            raise serializers.ValidationError("estimated_time must be greater than 0.")
        if value > 10080:
            raise serializers.ValidationError("estimated_time is too large.")
        return value

    def validate_description(self, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if len(value) > 5000:
            raise serializers.ValidationError("description is too long.")

        return value

    def validate(self, attrs):
        designed_by = attrs.get("designed_by")
        if designed_by and not getattr(designed_by, "is_active", True):
            raise serializers.ValidationError({
                "designed_by": "The selected user is inactive."
            })
        return attrs

class InputURLSerializer(serializers.ModelSerializer):
    scenarios = InputScenarioSerializer(many=True, required=False)

    class Meta:
        model = InputURL
        fields = [
            "id",
            "url",
            "created",
            "updated",
            "scenarios",
        ]
        read_only_fields = ["id", "created", "updated"]

    def validate_url(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("url cannot be empty.")

        if len(value) > 500:
            raise serializers.ValidationError("url is too long.")

        return value

    def create(self, validated_data):
        scenarios_data = validated_data.pop("scenarios", [])

        with transaction.atomic():
            url = InputURL.objects.create(**validated_data)

            for scenario_data in scenarios_data:
                InputScenario.objects.create(url=url, **scenario_data)

        return url

class InputFlowSerializer(serializers.ModelSerializer):
    urls = InputURLSerializer(many=True, required=False)

    class Meta:
        model = InputFlow
        fields = [
            "id",
            "flowName",
            "engagement",
            "created",
            "updated",
            "urls",
        ]
        read_only_fields = ["id", "created", "updated"]

    def validate_flowName(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("flowName cannot be empty.")

        if len(value) > 255:
            raise serializers.ValidationError("flowName is too long.")

        return value

    def validate(self, attrs):
        engagement = attrs.get("engagement")
        if engagement is None:
            raise serializers.ValidationError({
                "engagement": "engagement is required."
            })
        return attrs

    def create(self, validated_data):
        urls_data = validated_data.pop("urls", [])

        with transaction.atomic():
            flow = InputFlow.objects.create(**validated_data)

            for url_data in urls_data:
                scenarios_data = url_data.pop("scenarios", [])
                url = InputURL.objects.create(flow=flow, **url_data)

                for scenario_data in scenarios_data:
                    InputScenario.objects.create(url=url, **scenario_data)

        return flow
    
    