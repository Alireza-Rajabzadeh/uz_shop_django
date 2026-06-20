from django.contrib.auth import authenticate
from rest_framework import serializers


class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        user = authenticate(username=data["username"], password=data["password"])

        if not user:
            raise serializers.ValidationError("Invalid credentials")

        if not user.is_active:
            raise serializers.ValidationError("User is inactive")

        if not user.is_staff:
            raise serializers.ValidationError("Not an admin user")

        data["user"] = user
        return data
