from rest_framework import serializers


class SampleListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField(required=False, error_messages={"invalid": "Selecione uma fazenda válida."})
    cow = serializers.UUIDField(required=False, error_messages={"invalid": "Selecione uma vaca válida."})
    search = serializers.CharField(required=False, allow_blank=True, max_length=200, trim_whitespace=True)
