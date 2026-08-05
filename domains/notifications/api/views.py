from django.http import Http404
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.notifications.models import Provider, ProviderStatus, SentNotification
from domains.notifications.services import (
    NotificationError,
    NotificationService,
    ProviderService,
    SMSService,
)
from domains.users.auth import AdminJWTAuthentication

from .serializers import (
    ProviderListQuerySerializer,
    ProviderReadSerializer,
    ProviderStatusSerializer,
    ProviderWriteSerializer,
    SentNotificationListQuerySerializer,
    SentNotificationReadSerializer,
    SMSSendSerializer,
)


def service_call(callback):
    try:
        return callback()
    except NotificationError as exc:
        raise ValidationError(exc.errors) from exc


class NotificationAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def paginate(queryset, request, view, serializer_class):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=view)
        data = serializer_class(page, many=True).data
        return paginator.get_paginated_response(data).data


class ProviderList(NotificationAPIView):
    model = Provider

    def get(self, request):
        serializer = ProviderListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        values.pop("page", None)
        queryset = ProviderService().list(**values)
        data = self.paginate(queryset, request, self, ProviderReadSerializer)
        return api_response(data=data)


class ProviderDetail(NotificationAPIView):
    model = Provider

    @staticmethod
    def get_object(provider_id):
        try:
            return ProviderService.get(provider_id)
        except Provider.DoesNotExist as exc:
            raise NotFound("Provider not found.") from exc

    def get(self, request, provider_id):
        return api_response(data=ProviderReadSerializer(self.get_object(provider_id)).data)

    def patch(self, request, provider_id):
        provider = self.get_object(provider_id)
        serializer = ProviderWriteSerializer(provider, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        provider = service_call(
            lambda: ProviderService().update(provider, **serializer.validated_data)
        )
        return api_response(data=ProviderReadSerializer(provider).data)


class ProviderStatusList(NotificationAPIView):
    model = Provider

    def get(self, request):
        statuses = ProviderStatus.objects.order_by("id")
        return api_response(data=ProviderStatusSerializer(statuses, many=True).data)


class ProviderOptionList(NotificationAPIView):
    model = SentNotification

    def get(self, request):
        providers = Provider.objects.select_related("status").order_by("service_type", "name")
        return api_response(data=ProviderReadSerializer(providers, many=True).data)


class SentNotificationList(NotificationAPIView):
    model = SentNotification

    def get(self, request):
        serializer = SentNotificationListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        values.pop("page", None)
        queryset = NotificationService().list(**values)
        data = self.paginate(queryset, request, self, SentNotificationReadSerializer)
        return api_response(data=data)


class SentNotificationDetail(NotificationAPIView):
    model = SentNotification

    def get(self, request, notification_id):
        try:
            notification = NotificationService.get(notification_id)
        except (SentNotification.DoesNotExist, Http404) as exc:
            raise NotFound("Sent notification not found.") from exc
        return api_response(data=SentNotificationReadSerializer(notification).data)


class SMSSendPermissions(AdminModelPermissions):
    perms_map = {
        **AdminModelPermissions.perms_map,
        "POST": ["notifications.send_sms"],
    }


class NotificationQueueUnavailable(APIException):
    status_code = 503
    default_detail = "The SMS could not be queued."
    default_code = "notification_queue_unavailable"


class SMSSend(NotificationAPIView):
    model = SentNotification
    permission_classes = [SMSSendPermissions]

    def post(self, request):
        serializer = SMSSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification = service_call(
            lambda: SMSService().send(
                **serializer.validated_data,
                created_by=request.user,
            )
        )
        if notification.status == SentNotification.Status.FAILED:
            raise NotificationQueueUnavailable()
        return api_response(
            data=SentNotificationReadSerializer(notification).data,
            status_code=202,
        )
