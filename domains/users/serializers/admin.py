from django.contrib.auth import authenticate
from rest_framework import serializers


class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=150
    )
    
    password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True
    )

    
