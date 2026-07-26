from django.contrib.auth.models import Permission
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from core.responses import api_response
from .serializers import AdminLoginSerializer
from .services.auth_service import AuthService


class adminLogin(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = AuthService()
        result = service.authenticate_admin(
            serializer.validated_data["username"],
            serializer.validated_data["password"],
        )

        return api_response(True, '', result)


class UserPermissions(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        perms = Permission.objects.select_related("content_type").all().order_by("content_type__app_label", "codename")
        grouped = {}
        for p in perms:
            app = p.content_type.app_label
            if app not in grouped:
                grouped[app] = []
            grouped[app].append({
                "id": p.id,
                "codename": p.codename,
                "name": p.name,
            })
        return api_response(True, "", {
            "permissions": grouped,
            "user_permissions": list(getattr(request.user, "get_all_permissions", lambda: set())()),
        })
