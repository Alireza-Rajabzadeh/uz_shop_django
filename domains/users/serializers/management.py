from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group, Permission
from rest_framework import serializers


User = get_user_model()


class PermissionSummarySerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)
    model = serializers.CharField(source="content_type.model", read_only=True)
    full_codename = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ("id", "codename", "name", "app_label", "model", "full_codename")

    def get_full_codename(self, obj):
        return f"{obj.content_type.app_label}.{obj.codename}"


class RoleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("id", "name")


class AdminSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "is_active")


class AdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "is_active",
            "is_staff", "is_superuser", "last_login", "date_joined",
        )


class AdminWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    role_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )

    class Meta:
        model = User
        fields = (
            "username", "email", "first_name", "last_name", "password",
            "is_active", "is_staff", "is_superuser", "role_ids", "permission_ids",
        )
        extra_kwargs = {
            "email": {"required": True, "allow_blank": False},
            "is_active": {"required": False},
            "is_staff": {"required": False},
            "is_superuser": {"required": False},
        }

    def validate(self, attrs):
        if self.instance is None and "password" not in attrs:
            raise serializers.ValidationError({"password": "This field is required."})
        if self.instance is not None and "password" in attrs:
            raise serializers.ValidationError({
                "password": "Use the administrator password reset endpoint."
            })
        is_staff = attrs.get("is_staff", getattr(self.instance, "is_staff", True))
        is_superuser = attrs.get(
            "is_superuser", getattr(self.instance, "is_superuser", False)
        )
        if is_superuser and not is_staff:
            raise serializers.ValidationError(
                {"is_staff": "A superuser must retain admin panel access."}
            )
        password = attrs.get("password")
        if password:
            candidate = self.instance or User()
            for field in ("username", "email", "first_name", "last_name"):
                if field in attrs:
                    setattr(candidate, field, attrs[field])
            password_validation.validate_password(password, candidate)
        return attrs


class RoleSerializer(serializers.ModelSerializer):
    admin_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Group
        fields = ("id", "name", "admin_count")


class RoleWriteSerializer(serializers.ModelSerializer):
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )
    admin_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )

    class Meta:
        model = Group
        fields = ("name", "permission_ids", "admin_ids")


class RoleAssignmentSerializer(serializers.Serializer):
    role_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )


class PermissionAssignmentSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )


class AdminAssignmentSerializer(serializers.Serializer):
    admin_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )
