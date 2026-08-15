from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import LandingPage
from .serializers import LandingPageSerializer


class AdminContentAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def paginated(queryset, request, view, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=view)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data


class AdminLandingPageList(AdminContentAPIView):
    model = LandingPage

    def get(self, request):
        queryset = LandingPage.objects.all().order_by("-updated_at")
        data = self.paginated(queryset, request, self, LandingPageSerializer)
        return api_response(data=data)

    def post(self, request):
        serializer = LandingPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=LandingPageSerializer(page).data, status_code=201)
