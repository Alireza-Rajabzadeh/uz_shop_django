from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import PaymentChannel, PaymentMethod
from .serializers import (
    ChannelListQuerySerializer,
    ListQuerySerializer,
    PaymentChannelWriteSerializer,
    PaymentMethodReadSerializer,
    PaymentMethodUpdateSerializer,
)
from .services import PaymentService


service = PaymentService()


def service_call(callback):
    try:
        return callback()
    except PaymentService.ValidationError as exc:
        raise ValidationError(exc.errors) from exc
    except PaymentService.NotFoundError as exc:
        raise NotFound(str(exc)) from exc


class AdminPaymentAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def paginated(queryset, request, view, serializer=None, payload=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=view)
        data = payload(page) if payload else serializer(page, many=True).data
        return paginator.get_paginated_response(data).data


class AdminPaymentMethodList(AdminPaymentAPIView):
    model = PaymentMethod

    def get(self, request):
        query = ListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        channel_code = values.pop("channel_code", "")
        data = self.paginated(
            service.list_methods(**values), request, self,
            payload=lambda rows: PaymentMethodReadSerializer(
                rows, many=True, context={"channel_code": channel_code}
            ).data,
        )
        return api_response(data=data)


class AdminPaymentMethodDetail(AdminPaymentAPIView):
    model = PaymentMethod

    @staticmethod
    def get_object(method_id):
        try:
            return PaymentMethod.objects.get(id=method_id)
        except PaymentMethod.DoesNotExist as exc:
            raise NotFound("Payment method not found.") from exc

    def patch(self, request, method_id):
        method = self.get_object(method_id)
        serializer = PaymentMethodUpdateSerializer(method, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        service_call(lambda: service.validate_method_icon(serializer.validated_data.get("icon_file")))
        serializer.save()
        return api_response(data=PaymentMethodReadSerializer(method).data)


class AdminPaymentReviewPermissions(AdminModelPermissions):
    perms_map = {
        "POST": ["payments.change_payment"],
        "OPTIONS": [],
        "HEAD": [],
    }


class AdminPaymentReview(AdminPaymentAPIView):
    model = PaymentMethod
    permission_classes = [AdminPaymentReviewPermissions]

    def post(self, request, payment_id, decision):
        if decision not in {"approve", "reject"}:
            raise NotFound("Payment review action not found.")
        order = service_call(
            lambda: service.review_payment(
                payment_id, approve=decision == "approve", admin=request.user
            )
        )
        from domains.order.services import OrderService

        return api_response(data=OrderService().get_order_admin(order.id))


class AdminPaymentChannelList(AdminPaymentAPIView):
    model = PaymentChannel

    def get(self, request):
        query = ChannelListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        data = self.paginated(
            service.list_channels(**values), request, self,
            payload=lambda rows: [service.channel_payload(row, masked=True) for row in rows],
        )
        return api_response(data=data)

    def post(self, request):
        serializer = PaymentChannelWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        methods = values.pop("supported_methods_value", [])
        channel = service_call(lambda: service.create_channel(supported_methods=methods, **values))
        return api_response(data=service.channel_payload(channel, masked=False), status_code=201)


class PaymentChannelDetailPermissions(AdminModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.change_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
    }


class AdminPaymentChannelDetail(AdminPaymentAPIView):
    model = PaymentChannel
    permission_classes = [PaymentChannelDetailPermissions]

    def get(self, request, channel_id):
        channel = service_call(lambda: service.get_channel(channel_id))
        return api_response(data=service.channel_payload(channel, masked=False))

    def patch(self, request, channel_id):
        channel = service_call(lambda: service.get_channel(channel_id))
        serializer = PaymentChannelWriteSerializer(
            channel, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        methods = values.pop("supported_methods_value", None)
        channel = service_call(
            lambda: service.update_channel(channel, supported_methods=methods, **values)
        )
        return api_response(data=service.channel_payload(channel, masked=False))


class PaymentChannelMethodPermissions(AdminModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.change_%(model_name)s"],
    }


class AdminPaymentChannelMethods(AdminPaymentAPIView):
    model = PaymentChannel
    permission_classes = [PaymentChannelMethodPermissions]

    def post(self, request, channel_id):
        channel = service_call(lambda: service.get_channel(channel_id))
        serializer = PaymentChannelWriteSerializer(
            channel, data={"payment_method_ids": request.data.get("payment_method_ids")},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        methods = serializer.validated_data["supported_methods_value"]
        channel = service_call(
            lambda: service.update_channel(channel, supported_methods=methods)
        )
        return api_response(data=service.channel_payload(channel, masked=False))
