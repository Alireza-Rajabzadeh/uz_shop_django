from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication
from ..models.page import Page
from ..serializers.page_detail_serializer import PageDetailSerializer
from ..serializers.page_serializer import PageSerializer
from ..services.page_service import PageService


class AdminPageView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    model = Page
    ordering_fields = {"id", "title", "slug", "status", "created_at", "updated_at"}

    def check_permissions(self, request):
        super().check_permissions(request)
        action = self.kwargs.get("action")
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            self.permission_denied(request)

        if action == "publish":
            if not user.has_perm("content.change_page"):
                self.permission_denied(request)
            return

        method_perms = {
            "GET": ("content.view_page",),
            "POST": ("content.add_page",),
            "PATCH": ("content.change_page",),
            "DELETE": ("content.delete_page",),
        }
        required = method_perms.get(request.method, ())
        if not all(user.has_perm(perm) for perm in required):
            self.permission_denied(request)

    @staticmethod
    def get_page(page_id):
        try:
            return Page.objects.get(id=page_id)
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

    def paginate_queryset(self, queryset, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data

    def get(self, request, page_id=None, action=None):
        if page_id is not None:
            page = self.get_page(page_id)
            return api_response(data=PageDetailSerializer(page).data)

        ordering = request.query_params.get("ordering", "-updated_at")
        field = ordering.removeprefix("-")
        if field not in self.ordering_fields:
            ordering = "-updated_at"
        queryset = Page.objects.all().order_by(ordering)
        data = self.paginate_queryset(queryset, PageSerializer)
        return api_response(data=data)

    def post(self, request, page_id=None, action=None):
        if action == "publish":
            page = self.get_page(page_id)
            PageService().publish_page(page)
            return api_response(data=PageDetailSerializer(page).data)

        serializer = PageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=PageSerializer(page).data, status_code=201)

    def patch(self, request, page_id=None, action=None):
        page = self.get_page(page_id)
        serializer = PageSerializer(page, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=PageDetailSerializer(page).data)

    def delete(self, request, page_id=None, action=None):
        page = self.get_page(page_id)
        PageService().delete_page(page)
        return api_response(data=None)
