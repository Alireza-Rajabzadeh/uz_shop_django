from decimal import Decimal

from rest_framework import serializers

from domains.business.models import (
    BusinessPhone,
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessServiceMode,
    BusinessShipment,
    BusinessSocialLink,
    BusinessWorkingDay,
    SocialMedia,
    SocialMediaIcon,
)
from domains.files.models import File
from domains.files.services import FileService
from domains.location.models import City, State
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod


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

    # Location picks ride the location domain: the panel writes the ids its
    # province/city selects produced and reads back display titles.
    province_id = serializers.PrimaryKeyRelatedField(
        source="province",
        queryset=State.objects.all(),
        required=False,
        allow_null=True,
    )
    city_id = serializers.PrimaryKeyRelatedField(
        source="city",
        queryset=City.objects.all(),
        required=False,
        allow_null=True,
    )
    province = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()

    # Lifecycle state is admin-decided: readable so the panel can gate its
    # UX, but never writable — a vendor editing "business information"
    # must not be able to move itself out of `confirmation_await`.
    status = serializers.PrimaryKeyRelatedField(read_only=True)
    status_code = serializers.SerializerMethodField()

    class Meta:
        model = BusinessProfile
        fields = [
            "id", "business_name", "display_name", "legal_name", "email",
            "address", "province_id", "city_id", "province", "city",
            "postal_code", "latitude", "longitude",
            "light_logo_id", "light_logo", "dark_logo_id", "dark_logo",
            "enamad_link", "availability_status", "availability_message",
            "availability_until", "cache_ttl", "status", "status_code",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_status_code(self, obj):
        """`status`'s stable string code — the panel's gating contract."""
        return obj.status.code if obj.status_id else None

    def get_province(self, obj):
        if not obj.province_id:
            return None
        return {"id": obj.province_id, "title": obj.province.fa_title or obj.province.name}

    def get_city(self, obj):
        if not obj.city_id:
            return None
        return {"id": obj.city_id, "title": obj.city.fa_title or obj.city.name}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        # Partial updates only carry the changed keys, so resolve the
        # effective pair before checking that the city belongs to the
        # province standing next to it.
        province = (
            attrs["province"] if "province" in attrs
            else (instance.province if instance else None)
        )
        city = (
            attrs["city"] if "city" in attrs
            else (instance.city if instance else None)
        )
        if province and city and city.state_id != province.id:
            raise serializers.ValidationError(
                {"city_id": "The city does not belong to the selected province."}
            )
        return attrs

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
    title = serializers.CharField(required=False, allow_blank=True)
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
        if not validated_data.get("title"):
            social_media = validated_data.get("social_media")
            if social_media:
                validated_data["title"] = social_media.fa_name or social_media.name
            else:
                validated_data["title"] = validated_data.get("key", "link")
        return super().create(validated_data)


class VendorSocialLinkReorderSerializer(serializers.Serializer):
    social_links = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class VendorPhoneReorderSerializer(serializers.Serializer):
    phones = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


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
        return attrs


class VendorBusinessWorkingDayUpsertSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    is_open = serializers.BooleanField()
    opens_at = serializers.TimeField(required=False, allow_null=True, default=None)
    closes_at = serializers.TimeField(required=False, allow_null=True, default=None)
    second_opens_at = serializers.TimeField(required=False, allow_null=True, default=None)
    second_closes_at = serializers.TimeField(required=False, allow_null=True, default=None)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        is_open = attrs["is_open"]
        opens_at = attrs.get("opens_at")
        closes_at = attrs.get("closes_at")
        second_opens_at = attrs.get("second_opens_at")
        second_closes_at = attrs.get("second_closes_at")
        if is_open and (opens_at is None or closes_at is None or opens_at >= closes_at):
            raise serializers.ValidationError("Open days require opens_at before closes_at.")
        if not is_open and any([opens_at, closes_at, second_opens_at, second_closes_at]):
            raise serializers.ValidationError("Closed days cannot have time intervals.")
        if (second_opens_at is None) != (second_closes_at is None):
            raise serializers.ValidationError("Both second interval times are required.")
        if second_opens_at is not None and (second_opens_at >= second_closes_at or second_opens_at < closes_at):
            raise serializers.ValidationError("Second interval must be ordered and cannot overlap the first.")
        return attrs


class ShipmentMethodSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentMethod
        fields = ["id", "code", "name", "description", "is_active"]


class ShipmentPricingMethodSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentPricingMethod
        fields = ["id", "code", "name", "description", "is_active"]


class VendorBusinessShipmentSerializer(serializers.ModelSerializer):
    """One business's shipment configuration.

    Writes name the global rows by id; reads expand both references so the
    panel never has to join the shipping vocabulary itself.
    """

    shipment_method_id = serializers.PrimaryKeyRelatedField(
        source="shipment_method",
        queryset=ShipmentMethod.objects.all(),
        write_only=True,
    )
    pricing_method_id = serializers.PrimaryKeyRelatedField(
        source="pricing_method",
        queryset=ShipmentPricingMethod.objects.all(),
        write_only=True,
    )
    shipment_method = ShipmentMethodSummarySerializer(read_only=True)
    pricing_method = ShipmentPricingMethodSummarySerializer(read_only=True)

    class Meta:
        model = BusinessShipment
        fields = [
            "id",
            "shipment_method_id",
            "shipment_method",
            "pricing_method_id",
            "pricing_method",
            "cost",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "cost": {"min_value": Decimal("0.00")},
        }

    def validate(self, attrs):
        # Deactivating an existing default is allowed: the service clears the
        # default flag in the same transaction. Only an explicit request to
        # make an inactive configuration the default is contradictory.
        if attrs.get("is_default") is True:
            is_active = attrs.get(
                "is_active",
                self.instance.is_active if self.instance else True,
            )
            if not is_active:
                raise serializers.ValidationError(
                    {"is_default": "A default shipment method must be active."}
                )
        return attrs


class BusinessServiceModeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessServiceMode
        fields = ["id", "code", "name", "description", "is_active"]


class VendorBusinessServiceModeSerializer(serializers.ModelSerializer):
    service_mode = BusinessServiceModeSummarySerializer(read_only=True)

    class Meta:
        model = BusinessProfileServiceMode
        fields = [
            "id",
            "service_mode",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class VendorBusinessServiceModeCreateSerializer(serializers.Serializer):
    service_mode_id = serializers.PrimaryKeyRelatedField(
        source="service_mode",
        queryset=BusinessServiceMode.objects.all(),
    )


class VendorBusinessServiceModeUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
