from rest_framework import serializers

from domains.business.models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay


class ImmutableKeySerializer(serializers.ModelSerializer):
    def validate_key(self, value):
        if self.instance and value != self.instance.key:
            raise serializers.ValidationError("Key cannot be changed after creation.")
        return value


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance is None and BusinessProfile.objects.exists():
            raise serializers.ValidationError("Only one business profile may exist.")
        return attrs


class BusinessPhoneSerializer(ImmutableKeySerializer):
    class Meta:
        model = BusinessPhone
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class PublicBusinessPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessPhone
        fields = ["key", "title", "number", "extension", "position"]


class BusinessSocialLinkSerializer(ImmutableKeySerializer):
    class Meta:
        model = BusinessSocialLink
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class PublicBusinessSocialLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessSocialLink
        fields = ["key", "title", "platform", "url", "position"]


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
    class Meta:
        model = BusinessProfile
        exclude = ["cache_ttl", "created_at", "updated_at"]


class PublicBusinessWorkingDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessWorkingDay
        exclude = ["created_at", "updated_at"]
