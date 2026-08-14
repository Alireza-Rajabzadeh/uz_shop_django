from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.files.models import File
from domains.files.services import FileService
from domains.order.models import Order, OrderAction, OrderHistory, OrderStatus

from .models import (
    Payment, PaymentChannel, PaymentChannelSupportedMethod, PaymentDocument,
    PaymentMethod,
)
from .online_payment_providers import provider_availability


class PaymentService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    class NotFoundError(Exception):
        pass

    MANUAL_METHODS = ("card_to_card", "deposit_to_account")

    @staticmethod
    def method_availability(method, channel=None):
        if not method.is_active:
            return False, "Payment method is inactive."
        if channel is not None and not channel.is_active:
            return False, "Payment channel is inactive."
        if method.code == "online" and channel is not None:
            return provider_availability(channel.code)
        return True, None

    @staticmethod
    def file_payload(file):
        if file is None:
            return None
        try:
            url = FileService().url(file)
        except FileService.Error:
            url = None
        return {
            "id": str(file.id),
            "original_name": file.original_name,
            "content_type": file.content_type,
            "file_type": file.file_type,
            "url": url,
        }

    logo_payload = file_payload

    def customer_methods_payload(self):
        methods = PaymentMethod.objects.filter(is_active=True).prefetch_related(
            "supported_channels__payment_channel__logo_file__status"
        ).select_related("icon_file__status").order_by("id")
        payload = []
        for method in methods:
            channels = []
            reasons = []
            for support in method.supported_channels.all():
                channel = support.payment_channel
                available, reason = self.method_availability(method, channel)
                if not available:
                    if reason:
                        reasons.append(reason)
                    continue
                channel_data = self.channel_payload(channel, masked=False)
                channel_data.pop("extra_data", None)
                channels.append(channel_data)
            payload.append({
                "id": method.id,
                "code": method.code,
                "name": method.name,
                "fa_name": method.fa_name,
                "icon": self.file_payload(method.icon_file),
                "point_to_channel_field": method.point_to_channel_field,
                "requires_documents": method.requires_documents,
                "available": bool(channels) or method.code == "credit",
                "reason": (
                    reasons[0] if reasons and not channels
                    else "No available payment channel." if not channels and method.code != "credit"
                    else None
                ),
                "channels": channels,
            })
        return payload

    def confirm_manual_payment(
        self, customer, order_id, *, payment_method_code, payment_channel_id,
        ref_number=None, resource_account_number=None, documents=None,
    ):
        if self._expire_stale_order(customer, order_id):
            raise self.ValidationError({"order": [_("The order reservation has expired.")]})
        return self._confirm_manual_payment(
            customer, order_id, payment_method_code=payment_method_code,
            payment_channel_id=payment_channel_id, ref_number=ref_number,
            resource_account_number=resource_account_number, documents=documents or [],
        )

    @transaction.atomic
    def _expire_stale_order(self, customer, order_id):
        order = Order.objects.select_for_update().select_related("status").filter(
            id=order_id, customer=customer
        ).first()
        if (
            order is None
            or order.status.name != "payment_pending"
            or order.reservation_expires_at is None
            or order.reservation_expires_at > timezone.now()
        ):
            return False

        from domains.order.services import OrderService

        OrderService().expire_orders([order])
        return True

    @transaction.atomic
    def _confirm_manual_payment(
        self, customer, order_id, *, payment_method_code, payment_channel_id,
        ref_number=None, resource_account_number=None, documents,
    ):
        order = Order.objects.select_for_update().select_related("status").filter(
            id=order_id, customer=customer
        ).first()
        if order is None:
            raise self.NotFoundError("Order not found.")
        if order.status.name == "paid":
            return order
        if order.status.name == "payment_expired":
            raise self.ValidationError({"order": [_("The order reservation has expired.")]})
        if order.status.name != "payment_pending":
            raise self.ValidationError({"order": [_("This order cannot be paid.")]})
        if payment_method_code not in self.MANUAL_METHODS:
            raise self.ValidationError({
                "payment_method": [_("This payment method is not available for manual payment.")]
            })
        method = PaymentMethod.objects.filter(code=payment_method_code, is_active=True).first()
        if method is None:
            raise self.ValidationError({"payment_method": [_("This payment method is not available.")]})
        channel = PaymentChannel.objects.filter(id=payment_channel_id, is_active=True).first()
        if channel is None:
            raise self.ValidationError({"payment_channel": [_("This payment channel is not available.")]})
        if not PaymentChannelSupportedMethod.objects.filter(
            payment_channel=channel, payment_method=method
        ).exists():
            raise self.ValidationError({
                "payment_channel": [_("This channel does not support the selected payment method.")]
            })
        if method.requires_documents and not documents:
            raise self.ValidationError({"documents": [_("At least one payment document is required.")]})
        if len(documents) > 10:
            raise self.ValidationError({"documents": [_("No more than 10 payment documents are allowed.")]})
        payment = Payment.objects.create(
            order=order, payment_method=method, payment_channel=channel,
            amount=order.total_amount, status=Payment.Status.PENDING,
            ref_number=ref_number or "", resource_account_number=resource_account_number,
        )
        for document in documents:
            try:
                file = FileService().upload(
                    document,
                    metadata={"source": "payment_document", "order_id": order.id, "payment_id": payment.id},
                    object_prefix=f"orders/{order.id}/payments/{payment.id}",
                )
            except FileService.Error as exc:
                raise self.ValidationError({"documents": [str(exc)]}) from exc
            PaymentDocument.objects.create(payment=payment, file=file)
        order.status = OrderStatus.objects.get(name="payment_processing")
        order.reservation_expires_at = None
        order.save(update_fields=["status", "reservation_expires_at"])
        self._record_payment_history(
            order, "submit_payment", "Payment submitted by customer.", user=customer
        )
        return order

    @staticmethod
    def _record_payment_history(order, action_code, description, user=None):
        action = OrderAction.objects.get(code=action_code)
        OrderHistory.objects.create(
            order=order,
            action=action,
            user_id=user.pk if user is not None else None,
            user_model=user._meta.label if user is not None else None,
            before_values={},
            after_values={"status_id": order.status_id},
            description=description,
        )

    @transaction.atomic
    def review_payment(self, payment_id, *, approve, admin=None):
        payment = Payment.objects.select_for_update().select_related("order__status").filter(
            id=payment_id
        ).first()
        if payment is None:
            raise self.NotFoundError("Payment not found.")
        order = Order.objects.select_for_update().get(id=payment.order_id)
        if payment.status != Payment.Status.PENDING or order.status.name != "payment_processing":
            raise self.ValidationError({"payment": [_("This payment is not awaiting review.")]})
        if approve:
            payment.status = Payment.Status.SUCCESSFUL
            order.status = OrderStatus.objects.get(name="paid")
            order.successful_payment = payment
            order.save(update_fields=["status", "successful_payment"])
            self._consume_order_reservations(order)
            action_code = "approve_payment"
            description = "Payment approved by admin."
        else:
            payment.status = Payment.Status.FAILED
            order.status = OrderStatus.objects.get(name="payment_failed")
            order.save(update_fields=["status"])
            self._release_order_reservations(order)
            action_code = "reject_payment"
            description = "Payment rejected by admin."
        payment.save(update_fields=["status", "updated_at"])
        self._record_payment_history(order, action_code, description, user=admin)
        return order

    @staticmethod
    def _consume_order_reservations(order):
        from domains.order.services import OrderService

        OrderService().consume_reservations(order)

    @staticmethod
    def _release_order_reservations(order):
        from domains.order.services import OrderService

        OrderService().release_reservations(order)

    METHOD_ORDERING_FIELDS = {
        "code", "name", "fa_name", "is_active", "supported_channel_count",
    }
    CHANNEL_ORDERING_FIELDS = {
        "code", "name", "fa_name", "owner_name", "is_active", "payment_count",
        "created_at", "updated_at",
    }

    def list_methods(self, *, search="", is_active=None, ordering="id"):
        queryset = PaymentMethod.objects.annotate(
            supported_channel_count=Count("supported_channels", distinct=True)
        )
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search) | Q(name__icontains=search) | Q(fa_name__icontains=search)
            )
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if ordering.lstrip("-") not in self.METHOD_ORDERING_FIELDS:
            ordering = "id"
        return queryset.order_by(ordering, "id")

    def list_channels(
        self, *, search="", is_active=None, supported_method=None, ordering="id"
    ):
        queryset = PaymentChannel.objects.select_related(
            "logo_file__status"
        ).prefetch_related(
            "supported_methods__payment_method"
        ).annotate(
            payment_count=Count("payments", distinct=True)
        )
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search) | Q(name__icontains=search)
                | Q(fa_name__icontains=search) | Q(owner_name__icontains=search)
            )
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if supported_method is not None:
            queryset = queryset.filter(
                supported_methods__payment_method_id=supported_method
            )
        if ordering.lstrip("-") not in self.CHANNEL_ORDERING_FIELDS:
            ordering = "id"
        return queryset.distinct().order_by(ordering, "id")

    @staticmethod
    def _mask(value):
        if not value:
            return value
        return f"{'*' * max(len(value) - 4, 4)}{value[-4:]}"

    def channel_payload(self, channel, *, masked):
        methods = [support.payment_method for support in channel.supported_methods.all()]
        method_rows = []
        for method in methods:
            available, reason = self.method_availability(method, channel)
            method_rows.append({
                "id": method.id, "code": method.code, "name": method.name,
                "fa_name": method.fa_name, "icon": self.file_payload(method.icon_file),
                "point_to_channel_field": method.point_to_channel_field,
                "requires_documents": method.requires_documents,
                "is_active": method.is_active,
                "available": available, "reason": reason,
            })
        account_number = self._mask(channel.account_number) if masked else channel.account_number
        card_number = self._mask(channel.card_number) if masked else channel.card_number
        return {
            "id": channel.id, "code": channel.code, "name": channel.name,
            "fa_name": channel.fa_name,
            "account_number": account_number,
            "card_number": card_number,
            "masked_account_number": self._mask(channel.account_number),
            "masked_card_number": self._mask(channel.card_number),
            "owner_name": channel.owner_name, "extra_data": channel.extra_data,
            "is_active": channel.is_active, "logo": self.logo_payload(channel.logo_file),
            "supported_methods": method_rows,
            "payment_count": getattr(channel, "payment_count", channel.payments.count()),
            "created_at": channel.created_at.isoformat(), "updated_at": channel.updated_at.isoformat(),
        }

    @staticmethod
    def validate_logo(logo_file):
        if logo_file is None:
            return
        if logo_file.status.name != FileService.STATUS_AVAILABLE or logo_file.file_type != "image":
            raise PaymentService.ValidationError({"logo_file_id": ["Select an available image file."]})

    @staticmethod
    def validate_method_icon(icon_file):
        if icon_file is None:
            return
        if icon_file.status.name != FileService.STATUS_AVAILABLE or icon_file.file_type != "image":
            raise PaymentService.ValidationError({"icon_file_id": ["Select an available image file."]})

    @staticmethod
    def validate_supported_methods(channel_code, methods):
        online = next((method for method in methods if method.code == "online"), None)
        if online and online.is_active:
            available, reason = provider_availability(channel_code)
            if not available:
                raise PaymentService.ValidationError({"payment_method_ids": [reason]})

    @transaction.atomic
    def create_channel(self, *, supported_methods, **values):
        self.validate_logo(values.get("logo_file"))
        self.validate_supported_methods(values["code"], supported_methods)
        channel = PaymentChannel.objects.create(**values)
        PaymentChannelSupportedMethod.objects.bulk_create([
            PaymentChannelSupportedMethod(payment_channel=channel, payment_method=method)
            for method in supported_methods
        ])
        return self.get_channel(channel.id)

    @transaction.atomic
    def update_channel(self, channel, *, supported_methods=None, **values):
        if "logo_file" in values:
            self.validate_logo(values["logo_file"])
        methods = supported_methods
        if methods is not None:
            self.validate_supported_methods(channel.code, methods)
        for field, value in values.items():
            setattr(channel, field, value)
        channel.save()
        if methods is not None:
            channel.supported_methods.all().delete()
            PaymentChannelSupportedMethod.objects.bulk_create([
                PaymentChannelSupportedMethod(payment_channel=channel, payment_method=method)
                for method in methods
            ])
        return self.get_channel(channel.id)

    def get_channel(self, channel_id):
        try:
            return self.list_channels().get(id=channel_id)
        except PaymentChannel.DoesNotExist as exc:
            raise self.NotFoundError("Payment channel not found.") from exc
