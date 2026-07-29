from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.files.models import File, FileStatus
from domains.files.services import FileService
from domains.users.auth import AdminJWTAuthentication

from .serializers import (
    FileListQuerySerializer,
    FileMetadataSerializer,
    FileOrphanQuerySerializer,
    FileReadSerializer,
    FileStatusSerializer,
    FileUploadSerializer,
)


file_service = FileService()


class FilePagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class FileChangePermissions(AdminModelPermissions):
    perms_map = {
        **AdminModelPermissions.perms_map,
        "POST": ["%(app_label)s.change_%(model_name)s"],
    }


class AdminFileAPIView(APIView):
    model = File
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def service_error(exc):
        raise ValidationError(str(exc)) from exc

    @staticmethod
    def serialize_page(queryset, request, view):
        paginator = FilePagination()
        page = paginator.paginate_queryset(queryset, request, view=view)
        data = FileReadSerializer(page, many=True).data
        return paginator.get_paginated_response(data).data


class FileListCreate(AdminFileAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        query = FileListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        values.pop("page_size", None)
        try:
            files = file_service.list(**values)
        except FileService.Error as exc:
            self.service_error(exc)
        return api_response(True, "", self.serialize_page(files, request, self))

    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            file = file_service.upload(
                values["file"],
                storage_alias=values["storage_alias"],
                metadata=values["metadata"],
                created_by=request.user,
            )
        except FileService.Error as exc:
            self.service_error(exc)
        return api_response(True, "File uploaded.", FileReadSerializer(file).data, status_code=201)


class FileStatusList(AdminFileAPIView):
    def get(self, request):
        statuses = FileStatus.objects.order_by("name")
        return api_response(True, "", FileStatusSerializer(statuses, many=True).data)


class FileOrphanList(AdminFileAPIView):
    def get(self, request):
        query = FileOrphanQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        values.pop("page_size", None)
        try:
            files = file_service.orphans(**values)
        except FileService.Error as exc:
            self.service_error(exc)
        return api_response(True, "", self.serialize_page(files, request, self))


class FileDetail(AdminFileAPIView):
    parser_classes = [JSONParser]

    @staticmethod
    def get_object(file_id):
        try:
            return File.objects.select_related("status", "created_by").get(pk=file_id)
        except File.DoesNotExist as exc:
            raise NotFound("File not found.") from exc

    def get(self, request, file_id):
        return api_response(True, "", FileReadSerializer(self.get_object(file_id)).data)

    def patch(self, request, file_id):
        serializer = FileMetadataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = file_service.update_metadata(
            self.get_object(file_id), serializer.validated_data["metadata"]
        )
        return api_response(True, "File metadata updated.", FileReadSerializer(file).data)

    def delete(self, request, file_id):
        try:
            file = file_service.delete(self.get_object(file_id))
        except FileService.Error as exc:
            self.service_error(exc)
        return api_response(True, "File deleted.", FileReadSerializer(file).data)


class FileVerify(AdminFileAPIView):
    permission_classes = [FileChangePermissions]

    def post(self, request, file_id):
        file = FileDetail.get_object(file_id)
        try:
            file = file_service.verify(file)
        except FileService.Error as exc:
            self.service_error(exc)
        return api_response(True, "File verified.", FileReadSerializer(file).data)
