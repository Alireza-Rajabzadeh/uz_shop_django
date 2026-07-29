from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


User = get_user_model()


class StrictFieldsMixin:
    def to_internal_value(self, data):
        unknown_fields = set(data) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError({
                field: [_('This field is not allowed.')]
                for field in sorted(unknown_fields)
            })
        return super().to_internal_value(data)


class AdminProfileSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_superuser",
            "roles",
            "effective_permissions",
        )

    def get_roles(self, user):
        return [
            {"id": role.id, "name": role.name}
            for role in user.groups.order_by("name", "id")
        ]

    def get_effective_permissions(self, user):
        return sorted(user.get_all_permissions())


class AdminProfileUpdateSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    current_password = serializers.CharField(
        required=False,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "current_password",
        )
        extra_kwargs = {
            "username": {"required": False, "allow_blank": False},
            "email": {"required": False, "allow_blank": False},
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def validate_email(self, value):
        normalized = User.objects.normalize_email(value)
        if not normalized:
            raise serializers.ValidationError(_("This field may not be blank."))
        return normalized


class AdminPasswordChangeSerializer(StrictFieldsMixin, serializers.Serializer):
    current_password = serializers.CharField(
        allow_blank=False, trim_whitespace=False, write_only=True
    )
    new_password = serializers.CharField(
        allow_blank=False, trim_whitespace=False, write_only=True
    )
    new_password_confirmation = serializers.CharField(
        allow_blank=False, trim_whitespace=False, write_only=True
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirmation"]:
            raise serializers.ValidationError({
                "new_password_confirmation": _("Password confirmation does not match.")
            })
        return attrs
