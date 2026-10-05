from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import IsCustomer
from core.responses import api_response
from domains.payments.serializers import ConfirmPaymentSerializer
from domains.payments.services import PaymentService

from .serializers import ReturnRequestCreateSerializer, ReturnRequestSerializer
from .services import OrderService, ReturnRequestService


def _map_errors(exc):
    raise ValidationError(exc.errors) from exc


class OrderListCreateView(APIView):
    permission_classes = [IsCustomer]
    # Which flow this endpoint speaks to. A marketplace view subclasses this
    # class and swaps the three names; nothing below changes.
    order_service_class = OrderService

    def get(self, request):
        orders = self.order_service_class().list_orders(request.user)
        data = {
            "count": len(orders),
            "results": orders,
        }
        return api_response(True, "", data)

    def post(self, request):
        try:
            order = self.order_service_class().checkout_from_cart(request.user)
        except self.order_service_class.ValidationError as exc:
            _map_errors(exc)
        payload = self.order_service_class()._customer_order_payload(order)
        return api_response(True, _("Order created."), payload, status_code=201)


class OrderDetailView(APIView):
    permission_classes = [IsCustomer]
    order_service_class = OrderService

    def get(self, request, order_id):
        try:
            payload = self.order_service_class().get_order(request.user, order_id)
        except self.order_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return api_response(True, "", payload)


class OrderPaymentMethodsView(APIView):
    permission_classes = [IsCustomer]
    payment_service_class = PaymentService

    def get(self, request):
        methods = self.payment_service_class().customer_methods_payload()
        return api_response(data={"methods": methods})


class OrderConfirmPaymentView(APIView):
    permission_classes = [IsCustomer]
    payment_service_class = PaymentService
    order_service_class = OrderService

    def post(self, request, order_id):
        serializer = ConfirmPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            order = self.payment_service_class().confirm_manual_payment(
                request.user,
                order_id,
                payment_method_code=data["payment_method"],
                payment_channel_id=data["payment_channel_id"],
                ref_number=data.get("ref_number"),
                resource_account_number=data.get("resource_account_number"),
                documents=data.get("documents", []),
            )
        except self.payment_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except self.payment_service_class.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Payment submitted for review."),
            self.order_service_class()._customer_order_payload(order),
            status_code=202,
        )


class OrderActionsView(APIView):
    permission_classes = [IsCustomer]
    order_service_class = OrderService

    def get(self, request, order_id):
        try:
            actions = self.order_service_class().available_actions(
                order_id, actor="customer", customer=request.user
            )
        except self.order_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return api_response(data={"actions": actions})


class OrderExecuteActionView(APIView):
    permission_classes = [IsCustomer]
    order_service_class = OrderService

    def post(self, request, order_id, action_code):
        try:
            order = self.order_service_class().execute_action(
                order_id,
                action_code,
                actor="customer",
                customer=request.user,
            )
        except self.order_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except self.order_service_class.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            data=self.order_service_class()._customer_order_payload(order)
        )


class OrderCancelView(APIView):
    permission_classes = [IsCustomer]
    order_service_class = OrderService

    def post(self, request, order_id):
        try:
            order = self.order_service_class().cancel_order(request.user, order_id)
        except self.order_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except self.order_service_class.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Order cancelled."),
            self.order_service_class()._customer_order_payload(order),
        )


class ReturnRequestListCreateView(APIView):
    permission_classes = [IsCustomer]
    return_service_class = ReturnRequestService
    create_serializer = ReturnRequestCreateSerializer
    read_serializer = ReturnRequestSerializer

    def get(self, request):
        queryset = self.return_service_class().list(request.user)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": self.read_serializer(page, many=True).data,
        }
        return api_response(data=data)

    def post(self, request):
        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return_request = self.return_service_class().create(
                request.user,
                **serializer.validated_data,
            )
        except self.return_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except self.return_service_class.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Return request created."),
            self.read_serializer(return_request).data,
            status_code=201,
        )


class ReturnRequestDetailView(APIView):
    permission_classes = [IsCustomer]
    return_service_class = ReturnRequestService
    read_serializer = ReturnRequestSerializer

    def get(self, request, return_request_id):
        try:
            return_request = self.return_service_class().get(
                request.user,
                return_request_id,
            )
        except self.return_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return api_response(data=self.read_serializer(return_request).data)
