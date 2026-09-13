from rest_framework import serializers

from domains.business.models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay, SocialMedia, SocialMediaIcon
from domains.files.models import File
from domains.files.services import FileService


class VendorBusinessProfileSerializer(serializers.ModelSerializer):
    light_logo_id = serializers.PrimaryKeyRelatedField(
        source="light_logo",
        queryset=File.objects.select_related("status"),
        required=False,
        allow_null=True,
        write_only=True,
    )
    light_logo = serializers.SerializerMethodField()
    dark_logo_id = serializers.PrimaryKeyRelatedField(
        source="dark_logo",
        queryset=File.objects.select_related("status"),
        required=False,
        allow_null=True,
        write_only=True,
    )
    dark_logo = serializers.SerializerMethodField()

    class Meta:
        model = BusinessProfile
        fields = [
            "id", "business_name", "display_name", "legal_name", "email",
            "address", "postal_code", "latitude", "longitude",
            "light_logo_id", "light_logo", "dark_logo_id", "dark_logo",
            "enamad_link", "availability_status", "availability_message",
            "availability_until", "cache_ttl", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_light_logo_id(self, value):
        if value is not None and (
            value.status.name != FileService.STATUS_AVAILABLE or value.file_type != "image"
        ):
            raise serializers.ValidationError("Select an available image file.")
        return value

    def validate_dark_logo_id(self, value):
        if value is not None and (
            value.status.name != FileService.STATUS_AVAILABLE or value.file_type != "image"
        ):
            raise serializers.ValidationError("Select an available image file.")
        return value

    def _get_logo_info(self, file):
        if file is None:
            return None
        try:
            url = FileService().url(file)
        except FileService.Error:
            url = None
        return {
            "id": str(file.id),
            "original_name": file.original_name,
            "content_type": file.content_type,
            "file_type": file.file_type,
            "url": url,
        }

    def get_light_logo(self, obj):
        return self._get_logo_info(obj.light_logo)

    def get_dark_logo(self, obj):
        return self._get_logo_info(obj.dark_logo)


class VendorBusinessPhoneSerializer(serializers.ModelSerializer):
    key = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = BusinessPhone
        fields = [
            "id", "key", "title", "number", "extension",
            "visibility", "status", "notes", "position",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_key(self, value):
        if not value:
            return value
        if self.instance and value != self.instance.key:
            raise serializers.ValidationError("Key cannot be changed after creation.")
        business = self.context["business"]
        qs = BusinessPhone.objects.filter(business=business, key=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A phone with this key already exists.")
        return value

    def _generate_key(self, business):
        existing = set(
            BusinessPhone.objects.filter(business=business)
            .values_list("key", flat=True)
        )
        n = 1
        while f"phone-{n}" in existing:
            n += 1
        return f"phone-{n}"

    def create(self, validated_data):
        if not validated_data.get("key"):
            validated_data["key"] = self._generate_key(self.context["business"])
        return super().create(validated_data)


class VendorBusinessSocialLinkSerializer(serializers.ModelSerializer):
    key = serializers.CharField(required=False, allow_blank=True)
    social_media_id = serializers.PrimaryKeyRelatedField(
        source="social_media",
        queryset=SocialMedia.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    social_media = serializers.SerializerMethodField()
    icon_id = serializers.PrimaryKeyRelatedField(
        source="icon",
        queryset=SocialMediaIcon.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    icon = serializers.SerializerMethodField()

    class Meta:
        model = BusinessSocialLink
        fields = [
            "id", "key", "title", "social_media_id", "social_media",
            "url", "icon_id", "icon", "visibility", "status", "position",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_social_media(self, obj):
        if obj.social_media is None:
            return None
        return {
            "id": obj.social_media.id,
            "name": obj.social_media.name,
            "fa_name": obj.social_media.fa_name,
            "slug": obj.social_media.slug,
        }

    def get_icon(self, obj):
        if obj.icon is None:
            return None
        try:
            url = FileService().url(obj.icon.file)
        except FileService.Error:
            url = None
        return {
            "id": obj.icon.id,
            "label": obj.icon.label,
            "url": url,
        }

    def validate_key(self, value):
        if not value:
            return value
        if self.instance and value != self.instance.key:
            raise serializers.ValidationError("Key cannot be changed after creation.")
        business = self.context["business"]
        qs = BusinessSocialLink.objects.filter(business=business, key=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A social link with this key already exists.")
        return value

    def _generate_key(self, business):
        existing = set(
            BusinessSocialLink.objects.filter(business=business)
            .values_list("key", flat=True)
        )
        n = 1
        while f"social-link-{n}" in existing:
            n += 1
        return f"social-link-{n}"

    def create(self, validated_data):
        if not validated_data.get("key"):
            validated_data["key"] = self._generate_key(self.context["business"])
        return super().create(validated_data)


class VendorBusinessWorkingDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessWorkingDay
        fields = [
            "id", "weekday", "is_open", "opens_at", "closes_at",
            "second_opens_at", "second_closes_at", "description",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        values = {name: attrs.get(name, getattr(self.instance, name, None)) for name in ("is_open", "opens_at", "closes_at", "second_opens_at", "second_closes_at")}
        first = (values["opens_at"], values["closes_at"])
        second = (values["second_opens_at"], values["second_closes_at"])
        if values["is_open"] and (None in first or first[0] >= first[1]):
            raise serializers.ValidationError("Open days require opens_at before closes_at.")
        if not values["is_open"] and any(first + second):
            raise serializers.ValidationError("Closed days cannot have time intervals.")
        if (second[0] is None) != (second[1] is None):
            raise serializers.ValidationError("Both second interval times are required.")
        if second[0] is not None and (second[0] >= second[1] or second[0] < first[1]):
            raise serializers.ValidationError("Second interval must be ordered and cannot overlap the first.")
        weekday = attrs.get("weekday", getattr(self.instance, "weekday", None))
        if weekday is not None:
            vendor = self.context["vendor"]
            qs = BusinessWorkingDay.objects.filter(vendor=vendor, weekday=weekday)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"weekday": "A working day for this weekday already exists."})
        return attrs
