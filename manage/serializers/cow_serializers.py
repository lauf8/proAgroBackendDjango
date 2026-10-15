from django.db import IntegrityError
from rest_framework import serializers

from manage.models import Cow
from manage.services.cow_service import create_cow, update_cow


class CowDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cow
        fields = (
            "id", "farm", "name", "identifier", "birth_date", "breed", "status",
            "notes", "created_at", "updated_at",
        )
        read_only_fields = fields


class CowWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cow
        fields = (
            "id", "farm", "name", "identifier", "birth_date", "breed", "status",
            "notes", "created_at", "updated_at",
        )
        read_only_fields = ("id", "farm", "created_at", "updated_at")
        validators = []

    def validate_identifier(self, value):
        cows = Cow.objects.filter(farm=self.context["farm"], identifier=value)
        if self.instance is not None:
            cows = cows.exclude(pk=self.instance.pk)
        if cows.exists():
            raise serializers.ValidationError("Já existe uma vaca com este brinco nesta fazenda.")
        return value

    def create(self, validated_data):
        return create_cow(farm=self.context["farm"], cow_data=validated_data)

    def update(self, instance, validated_data):
        return update_cow(cow=instance, cow_data=validated_data)

    def save(self, **kwargs):
        try:
            return super().save(**kwargs)
        except IntegrityError as error:
            constraint_name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            if constraint_name == "unique_farm_cow_identifier":
                raise serializers.ValidationError({
                    "identifier": ["Já existe uma vaca com este brinco nesta fazenda."],
                }) from error
            raise


class CowListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Cow.Status.choices, required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)
