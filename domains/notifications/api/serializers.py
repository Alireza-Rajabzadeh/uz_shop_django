from rest_framework import serializers

from domains.notifications.models import Provider, ProviderStatus, SentNotification


class ProviderStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderStatus
        fields = ["id", "code", "name"]


class ProviderReadSerializer(serializers.ModelSerializer):
    status = ProviderStatusSerializer(read_only=True)
    service_type_label = serializers.CharField(source="get_service_type_display", read_only=True)

    class Meta:
        model = Provider
        fields = [
            "id", "name", "code", "service_type", "service_type_label", "status",
            "is_default", "created_at", "updated_at",
        ]


class ProviderWriteSerializer(serializers.ModelSerializer):
    status_id = serializers.PrimaryKeyRelatedField(
        source="status",
        queryset=ProviderStatus.objects.all(),
        required=False,
    )

    class Meta:
        model = Provider
        fields = ["name", "status_id", "is_default"]

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field is not mutable." for key in unknown}
            )
        return super().to_internal_value(data)


class ProviderListQuerySerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    service_type = serializers.ChoiceField(required=False, choices=Provider.ServiceType.values)
    status_id = serializers.IntegerField(required=False, min_value=1)
    is_default = serializers.ChoiceField(required=False, choices=["true", "false"])
    ordering = serializers.ChoiceField(
        required=False,
        default="id",
        choices=[
            "id", "-id", "name", "-name", "service_type", "-service_type",
            "status_name", "-status_name", "is_default", "-is_default",
            "created_at", "-created_at",
        ],
    )
    page = serializers.IntegerField(required=False, min_value=1)

    def validate_is_default(self, value):
        return value == "true"


class SentNotificationReadSerializer(serializers.ModelSerializer):
    provider_id = serializers.IntegerField(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = SentNotification
        fields = [
            "id", "service_type", "receiver", "message", "provider_id",
            "provider_code", "provider_name", "status", "external_id", "error_message",
            "created_by", "created_by_name", "created_at", "started_at", "sent_at",
            "delivered_at", "updated_at",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_username() if obj.created_by else None

    def get_message(self, obj):
        return "[redacted]" if obj.is_sensitive else obj.message


class SentNotificationListQuerySerializer(serializers.Serializer):
    receiver = serializers.CharField(required=False, allow_blank=True, max_length=320)
    provider_id = serializers.IntegerField(required=False, min_value=1)
    service_type = serializers.ChoiceField(required=False, choices=Provider.ServiceType.values)
    status = serializers.ChoiceField(required=False, choices=SentNotification.Status.values)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)
    ordering = serializers.ChoiceField(
        required=False,
        default="-created_at",
        choices=[
            "created_at", "-created_at", "updated_at", "-updated_at",
            "receiver", "-receiver", "service_type", "-service_type",
            "provider_name", "-provider_name", "status", "-status",
        ],
    )
    page = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if attrs.get("created_from") and attrs.get("created_to"):
            if attrs["created_from"] > attrs["created_to"]:
                raise serializers.ValidationError(
                    {"created_to": "End date must be on or after start date."}
                )
        return attrs


class SMSSendSerializer(serializers.Serializer):
    receiver = serializers.CharField(max_length=20)
    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    provider_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
