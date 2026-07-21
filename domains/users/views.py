from rest_framework.views import APIView
from django.utils.translation import gettext as _
# from rest_framework.decorators import api_view
from core.responses import api_response
# from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import AdminLoginSerializer
from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from django.conf import settings
import time
from django.contrib.auth import get_user_model
class adminLogin(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        
        User = get_user_model()

        start = time.perf_counter()
        user = User.objects.filter(username=serializer.validated_data["username"]).first()
        print("Database:", time.perf_counter() - start)

        start = time.perf_counter()
        result = user.check_password(serializer.validated_data["password"]) if user else False
        print("Password:", time.perf_counter() - start)
        
        
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]
        print(settings.PASSWORD_HASHERS)
        user = authenticate(
            request=request,
            username=username,
            password=password
            )
        print(2)
        
        if user is None:
            raise AuthenticationFailed("Invalid username or password.")
        
        if not user.is_staff:
            raise PermissionDenied("You do not have permission to access this resource.")
        refresh = RefreshToken.for_user(user)
        if not user.is_active:
            raise ValidationError("User account is inactive.")
        
        return api_response(
            True,
            '',
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            },
        )
