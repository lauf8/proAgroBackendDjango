from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from accounts.models import FarmMembership
from manage.models import Farm
from manage.services.farm_service import create_farm_with_owner


class FarmOwnerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        User = get_user_model()
        email = User.objects.normalize_email(value).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def validate(self, attrs):
        user = get_user_model()(name=attrs["name"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        return attrs


class FarmCreateSerializer(serializers.ModelSerializer):
    admin = FarmOwnerCreateSerializer(write_only=True)

    class Meta:
        model = Farm
        fields = (
            "id", "name", "owner_name", "city", "state", "phone", "notes",
            "is_active", "admin", "created_at", "updated_at",
        )
        read_only_fields = ("id", "is_active", "created_at", "updated_at")

    def create(self, validated_data):
        owner_data = validated_data.pop("admin")
        try:
            return create_farm_with_owner(validated_data, owner_data)
        except IntegrityError as error:
            constraint_name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            if constraint_name in ("unique_user_email_case_insensitive", "accounts_user_email_key"):
                raise serializers.ValidationError({
                    "admin": {"email": ["Já existe um usuário com este e-mail."]},
                }) from error
            raise


class FarmDetailSerializer(serializers.ModelSerializer):
    owner_email = serializers.SerializerMethodField()

    class Meta:
        model = Farm
        fields = (
            "id", "name", "owner_name", "owner_email", "city", "state", "phone",
            "notes", "is_active", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_owner_email(self, obj):
        memberships = getattr(obj, "active_owner_memberships", None)
        if memberships is None:
            membership = obj.memberships.filter(
                role=FarmMembership.Role.OWNER, is_active=True,
            ).select_related("user").order_by("created_at", "id").first()
        else:
            membership = memberships[0] if memberships else None
        return membership.user.email if membership else None


class FarmUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Farm
        fields = (
            "id", "name", "owner_name", "city", "state", "phone", "notes",
            "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_is_active(self, value):
        if not self.context["request"].user.is_superuser and value != self.instance.is_active:
            raise PermissionDenied({"is_active": ["Somente superusuários podem alterar a situação da fazenda."]})
        return value

    def update(self, instance, validated_data):
        if not self.context["request"].user.is_superuser:
            validated_data.pop("is_active", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data, "updated_at"])
        return instance


class FarmListQuerySerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
