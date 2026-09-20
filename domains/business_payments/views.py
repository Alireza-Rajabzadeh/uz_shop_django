from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.vendor.auth import VendorJWTAuthentication

from .models import BusinessPaymentChannel, BusinessPaymentMethod
from .serializers import (
    BusinessPaymentChannelWriteSerializer,
    BusinessPaymentMethodReadSerializer,
    BusinessPaymentMethodUpdateSerializer,
    ChannelListQuerySerializer,
    ConfirmPaymentSerializer,
    ListQuerySerializer,
    PaymentListQuerySerializer,
)
from .services import BusinessPaymentService, resolve_business


service = BusinessPaymentService()


def service_call(callback):
    try:
        return callback()
    except BusinessPaymentService.ValidationError as exc:
        raise ValidationError(exc.errors) from exc
    except BusinessPaymentService.NotFoundError as exc:
        raise NotFound(str(exc)) from exc


class BusinessPaymentAPIView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_business(self, request):
        try:
            return resolve_business(request.user)
        except BusinessPaymentService.NotFoundError as exc:
            raise NotFound(str(exc)) from exc

    @staticmethod
    def paginated(queryset, request, view, serializer=None, payload=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=view)
        data = payload(page) if payload else serializer(page, many=True).data
        return paginator.get_paginated_response(data).data


class VendorBusinessPaymentMethodList(BusinessPaymentAPIView):
    def get(self, request):
        business = self._get_business(request)
        query = ListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        channel_code = values.pop("channel_code", "")
        data = self.paginated(
            service.list_methods(business, **values),
            request,
            self,
            payload=lambda rows: BusinessPaymentMethodReadSerializer(
                rows, many=True, context={"channel_code": channel_code}
            ).data,
        )
        return api_response(data=data)


class VendorBusinessPaymentMethodDetail(BusinessPaymentAPIView):
    @staticmethod
    def get_object(business, method_id):
        try:
            return BusinessPaymentMethod.objects.get(id=method_id, business=business)
        except BusinessPaymentMethod.DoesNotExist as exc:
            raise NotFound("Payment method not found.") from exc

    def get(self, request, method_id):
        business = self._get_business(request)
        method = self.get_object(business, method_id)
        return api_response(
            data=BusinessPaymentMethodReadSerializer(method).data
        )

    def patch(self, request, method_id):
        business = self._get_business(request)
        method = self.get_object(business, method_id)
        serializer = BusinessPaymentMethodUpdateSerializer(
            method, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        service_call(
            lambda: service.validate_method_icon(
                serializer.validated_data.get("icon_file")
            )
        )
        serializer.save()
        return api_response(
            data=BusinessPaymentMethodReadSerializer(method).data
        )


class VendorBusinessPaymentChannelList(BusinessPaymentAPIView):
    def get(self, request):
        business = self._get_business(request)
        query = ChannelListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        data = self.paginated(
            service.list_channels(business, **values),
            request,
            self,
            payload=lambda rows: [
                service.channel_payload(row, masked=True) for row in rows
            ],
        )
        return api_response(data=data)

    def post(self, request):
        business = self._get_business(request)
        serializer = BusinessPaymentChannelWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        methods = values.pop("payment_method_ids", [])
        channel = service_call(
            lambda: service.create_channel(
                business, supported_methods=methods, **values
            )
        )
        return api_response(
            data=service.channel_payload(channel, masked=False), status_code=201
        )


class VendorBusinessPaymentChannelDetail(BusinessPaymentAPIView):
    def get(self, request, channel_id):
        business = self._get_business(request)
        channel = service_call(lambda: service.get_channel(business, channel_id))
        return api_response(
            data=service.channel_payload(channel, masked=False)
        )

    def patch(self, request, channel_id):
        business = self._get_business(request)
        channel = service_call(lambda: service.get_channel(business, channel_id))
        serializer = BusinessPaymentChannelWriteSerializer(
            channel, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        methods = values.pop("payment_method_ids", None)
        channel = service_call(
            lambda: service.update_channel(
                business, channel, supported_methods=methods, **values
            )
        )
        return api_response(
            data=service.channel_payload(channel, masked=False)
        )


class VendorBusinessPaymentChannelMethods(BusinessPaymentAPIView):
    def post(self, request, channel_id):
        business = self._get_business(request)
        channel = service_call(lambda: service.get_channel(business, channel_id))
        serializer = BusinessPaymentChannelWriteSerializer(
            channel,
            data={"payment_method_ids": request.data.get("payment_method_ids")},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        methods = serializer.validated_data["payment_method_ids"]
        channel = service_call(
            lambda: service.update_channel(
                business, channel, supported_methods=methods
            )
        )
        return api_response(
            data=service.channel_payload(channel, masked=False)
        )


class VendorBusinessPaymentList(BusinessPaymentAPIView):
    def get(self, request):
        business = self._get_business(request)
        query = PaymentListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        values.pop("page", None)
        status_filter = values.pop("status", None)
        if status_filter == "":
            status_filter = None
        data = self.paginated(
            service.list_payments(business, status=status_filter, **values),
            request,
            self,
            payload=lambda rows: [
                service.payment_payload(row) for row in rows
            ],
        )
        return api_response(data=data)


class VendorBusinessPaymentDetail(BusinessPaymentAPIView):
    def get(self, request, payment_id):
        business = self._get_business(request)
        payment = service_call(
            lambda: service.get_payment(business, payment_id)
        )
        return api_response(data=service.payment_payload(payment))


class VendorBusinessPaymentDocumentList(BusinessPaymentAPIView):
    def get(self, request, payment_id):
        business = self._get_business(request)
        documents = service_call(
            lambda: service.list_documents(business, payment_id)
        )
        data = [service.document_payload(doc) for doc in documents]
        return api_response(data=data)
