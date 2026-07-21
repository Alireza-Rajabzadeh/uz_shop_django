from rest_framework.views import APIView
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
