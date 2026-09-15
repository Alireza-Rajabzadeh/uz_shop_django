from rest_framework import serializers

from domains.business.models import BusinessCategory, BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay, SocialMedia, SocialMediaIcon
from domains.files.models import File
from domains.files.services import FileService


class ImmutableKeySerializer(serializers.ModelSerializer):
    def validate_key(self, value):
        if self.instance and value != self.instance.key:
            raise serializers.ValidationError("Key cannot be changed after creation.")
        return value


class BusinessProfileSerializer(serializers.ModelSerializer):
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
        fields = "__all__"
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


class BusinessPhoneSerializer(ImmutableKeySerializer):
    class Meta:
        model = BusinessPhone
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class PublicBusinessPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessPhone
        fields = ["key", "title", "number", "extension", "position"]


class SocialMediaIconSerializer(serializers.ModelSerializer):
    file_id = serializers.PrimaryKeyRelatedField(
        source="file",
        queryset=File.objects.select_related("status"),
        write_only=True,
    )
    file = serializers.SerializerMethodField()

    class Meta:
        model = SocialMediaIcon
        fields = ["id", "file_id", "file", "label", "position", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_file_id(self, value):
        if value.status.name != FileService.STATUS_AVAILABLE or value.file_type != "image":
            raise serializers.ValidationError("Select an available image file.")
        return value

    def get_file(self, obj):
        file = obj.file
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


class SocialMediaSerializer(serializers.ModelSerializer):
    icons = SocialMediaIconSerializer(many=True, read_only=True)

    class Meta:
        model = SocialMedia
        fields = ["id", "name", "fa_name", "slug", "is_active", "position", "icons", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PublicSocialMediaSerializer(serializers.ModelSerializer):
    icons = serializers.SerializerMethodField()

    class Meta:
        model = SocialMedia
        fields = ["id", "name", "fa_name", "slug", "position", "icons"]

    def get_icons(self, obj):
        icons = obj.icons.all()
        result = []
        for icon in icons:
            try:
                url = FileService().url(icon.file)
            except FileService.Error:
                url = None
            result.append({
                "id": icon.id,
                "label": icon.label,
                "url": url,
                "position": icon.position,
            })
        return result


class BusinessSocialLinkSerializer(ImmutableKeySerializer):
    social_media_id = serializers.PrimaryKeyRelatedField(
        source="social_media",
        queryset=SocialMedia.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    social_media = PublicSocialMediaSerializer(read_only=True)
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
            "url", "icon_id", "icon", "visibility", "status",
            "position", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

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


class PublicBusinessSocialLinkSerializer(serializers.ModelSerializer):
    social_media = PublicSocialMediaSerializer(read_only=True)
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessSocialLink
        fields = ["key", "title", "social_media", "url", "icon_url", "position"]

    def get_icon_url(self, obj):
        if obj.icon is None:
            return None
        try:
            return FileService().url(obj.icon.file)
        except FileService.Error:
            return None


class BusinessWorkingDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessWorkingDay
        fields = "__all__"
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


class PublicBusinessProfileSerializer(serializers.ModelSerializer):
    light_logo_url = serializers.SerializerMethodField()
    dark_logo_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessProfile
        exclude = ["cache_ttl", "created_at", "updated_at"]

    def _get_logo_url(self, file):
        if file is None:
            return None
        try:
            return FileService().url(file)
        except FileService.Error:
            return None

    def get_light_logo_url(self, obj):
        return self._get_logo_url(obj.light_logo)

    def get_dark_logo_url(self, obj):
        return self._get_logo_url(obj.dark_logo)


class PublicBusinessWorkingDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessWorkingDay
        exclude = ["created_at", "updated_at"]


class BusinessCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_fa_name = serializers.CharField(source="category.fa_name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)

    class Meta:
        model = BusinessCategory
        fields = ["id", "category", "category_name", "category_fa_name", "category_slug", "created_at"]
        read_only_fields = ["id", "created_at"]


class BusinessCategoryUpsertSerializer(serializers.Serializer):
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )

    def validate_category_ids(self, value):
        from domains.catalog.models import Category

        existing = set(Category.objects.filter(id__in=value).values_list("id", flat=True))
        missing = set(value) - existing
        if missing:
            raise serializers.ValidationError(f"Category IDs not found: {sorted(missing)}")

        non_roots = set(
            Category.objects.filter(id__in=value, parent__isnull=False)
            .values_list("id", flat=True)
        )
        if non_roots:
            raise serializers.ValidationError(
                f"Only root categories can be selected. Child category IDs: {sorted(non_roots)}"
            )
        return value


class CategoryBrowseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    fa_name = serializers.CharField(allow_null=True)
    slug = serializers.SlugField()
    has_children = serializers.BooleanField()
    selected = serializers.BooleanField()
