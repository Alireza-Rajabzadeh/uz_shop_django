import re
from uuid import uuid4

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from core.utils.transliteration import to_english_letters
from domains.business.models import BusinessProfile
from domains.files.models import File
from domains.files.services import FileService
from domains.order.models import Order, OrderAction, OrderHistory, OrderStatus

from .models import (
    BusinessPayment,
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentDocument,
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)
from .online_payment_providers import provider_availability


def resolve_business(vendor):
    business = BusinessProfile.objects.filter(vendor=vendor).first()
    if not business:
        raise BusinessPaymentService.NotFoundError("Business profile not found.")
    return business


class BusinessPaymentService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    class NotFoundError(Exception):
        pass

    MANUAL_METHODS = ("card_to_card", "deposit_to_account")

    @staticmethod
    def _status(name):
        return BusinessPaymentStatus.objects.get(name=name)

    @staticmethod
    def has_available_channel():
        methods = BusinessPaymentMethod.objects.filter(
            is_active=True
        ).prefetch_related("supported_channels__payment_channel")
        for method in methods:
            for support in method.supported_channels.all():
                available, _ = BusinessPaymentService.method_availability(
                    method, support.payment_channel
                )
                if available:
                    return True
        return False

    @staticmethod
    def method_availability(method, channel=None):
        if not method.is_active:
            return False, "Payment method is inactive."
        if channel is not None:
            if not channel.is_active:
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
        methods = BusinessPaymentMethod.objects.filter(
            is_active=True
        ).prefetch_related(
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
                "description": method.description,
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
        self, business, customer, order_id, *, payment_method_code,
        payment_channel_id, ref_number=None, resource_account_number=None,
        documents=None,
    ):
        if self._expire_stale_order(business, customer, order_id):
            raise self.ValidationError(
                {"order": [_("The order reservation has expired.")]}
            )
        return self._confirm_manual_payment(
            business, customer, order_id,
            payment_method_code=payment_method_code,
            payment_channel_id=payment_channel_id,
            ref_number=ref_number,
            resource_account_number=resource_account_number,
            documents=documents or [],
        )

    @transaction.atomic
    def _expire_stale_order(self, business, customer, order_id):
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
        self, business, customer, order_id, *, payment_method_code,
        payment_channel_id, ref_number, resource_account_number, documents,
    ):
        order = Order.objects.select_for_update().select_related("status").filter(
            id=order_id, customer=customer
        ).first()
        if order is None:
            raise self.NotFoundError("Order not found.")
        if order.status.name == "paid":
            return order
        if order.status.name == "payment_expired":
            raise self.ValidationError(
                {"order": [_("The order reservation has expired.")]}
            )
        if order.status.name != "payment_pending":
            raise self.ValidationError(
                {"order": [_("This order cannot be paid.")]}
            )
        if payment_method_code not in self.MANUAL_METHODS:
            raise self.ValidationError({
                "payment_method": [_(
                    "This payment method is not available for manual payment."
                )]
            })
        method = BusinessPaymentMethod.objects.filter(
            code=payment_method_code, is_active=True
        ).first()
        if method is None:
            raise self.ValidationError(
                {"payment_method": [_("This payment method is not available.")]}
            )
        channel = BusinessPaymentChannel.objects.filter(
            id=payment_channel_id, business=business, is_active=True
        ).first()
        if channel is None:
            raise self.ValidationError(
                {"payment_channel": [_("This payment channel is not available.")]}
            )
        if not BusinessPaymentChannelSupportedMethod.objects.filter(
            payment_channel=channel, payment_method=method
        ).exists():
            raise self.ValidationError({
                "payment_channel": [_(
                    "This channel does not support the selected payment method."
                )]
            })
        if method.requires_documents and not documents:
            raise self.ValidationError(
                {"documents": [_("At least one payment document is required.")]}
            )
        if len(documents) > 10:
            raise self.ValidationError(
                {"documents": [_("No more than 10 payment documents are allowed.")]}
            )
        payment = BusinessPayment.objects.create(
            business=business, order=order, payment_method=method,
            payment_channel=channel, amount=order.total_amount,
            status=self._status("pending"),
            ref_number=ref_number or "",
            resource_account_number=resource_account_number,
        )
        for document in documents:
            try:
                file = FileService().upload(
                    document,
                    metadata={
                        "source": "business_payment_document",
                        "order_id": order.id,
                        "payment_id": payment.id,
                    },
                    object_prefix=f"business-orders/{order.id}/payments/{payment.id}",
                )
            except FileService.Error as exc:
                raise self.ValidationError({"documents": [str(exc)]}) from exc
            BusinessPaymentDocument.objects.create(payment=payment, file=file)
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
    def review_payment(self, business, payment_id, *, approve, admin=None):
        payment = BusinessPayment.objects.select_for_update().select_related(
            "order__status", "status"
        ).filter(id=payment_id, business=business).first()
        if payment is None:
            raise self.NotFoundError("Payment not found.")
        order = Order.objects.select_for_update().get(id=payment.order_id)
        if (
            payment.status.name != "pending"
            or order.status.name != "payment_processing"
        ):
            raise self.ValidationError(
                {"payment": [_("This payment is not awaiting review.")]}
            )
        if approve:
            payment.status = self._status("successful")
            order.status = OrderStatus.objects.get(name="paid")
            order.save(update_fields=["status"])
            self._consume_order_reservations(order)
            action_code = "approve_payment"
            description = "Payment approved."
        else:
            payment.status = self._status("failed")
            order.status = OrderStatus.objects.get(name="payment_failed")
            order.save(update_fields=["status"])
            self._release_order_reservations(order)
            action_code = "reject_payment"
            description = "Payment rejected."
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

    def list_methods(
        self, *, search="", is_active=None, has_point_to_channel=None,
        ordering="id",
    ):
        queryset = BusinessPaymentMethod.objects.all().annotate(
            supported_channel_count=Count("supported_channels", distinct=True)
        )
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(fa_name__icontains=search)
                | Q(description__icontains=search)
            )
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if has_point_to_channel is not None:
            queryset = queryset.filter(
                point_to_channel_field__isnull=not has_point_to_channel
            )
        if ordering.lstrip("-") not in self.METHOD_ORDERING_FIELDS:
            ordering = "id"
        return queryset.order_by(ordering, "id")

    def list_channels(
        self, business, *, search="", is_active=None, supported_method=None,
        ordering="id",
    ):
        queryset = BusinessPaymentChannel.objects.filter(
            business=business
        ).select_related(
            "logo_file__status"
        ).prefetch_related(
            "supported_methods__payment_method"
        ).annotate(
            payment_count=Count("payments", distinct=True)
        )
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(fa_name__icontains=search)
                | Q(owner_name__icontains=search)
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
        methods = [
            support.payment_method for support in channel.supported_methods.all()
        ]
        method_rows = []
        for method in methods:
            available, reason = self.method_availability(method, channel)
            method_rows.append({
                "id": method.id,
                "code": method.code,
                "name": method.name,
                "fa_name": method.fa_name,
                "description": method.description,
                "icon": self.file_payload(method.icon_file),
                "point_to_channel_field": method.point_to_channel_field,
                "requires_documents": method.requires_documents,
                "is_active": method.is_active,
                "available": available,
                "reason": reason,
            })
        account_number = (
            self._mask(channel.account_number) if masked else channel.account_number
        )
        card_number = (
            self._mask(channel.card_number) if masked else channel.card_number
        )
        return {
            "id": channel.id,
            "code": channel.code,
            "name": channel.name,
            "fa_name": channel.fa_name,
            "account_number": account_number,
            "card_number": card_number,
            "masked_account_number": self._mask(channel.account_number),
            "masked_card_number": self._mask(channel.card_number),
            "owner_name": channel.owner_name,
            "extra_data": channel.extra_data,
            "is_active": channel.is_active,
            "logo": self.logo_payload(channel.logo_file),
            "supported_methods": method_rows,
            "payment_count": getattr(
                channel, "payment_count", channel.payments.count()
            ),
            "created_at": channel.created_at.isoformat(),
            "updated_at": channel.updated_at.isoformat(),
        }

    @staticmethod
    def validate_logo(logo_file):
        if logo_file is None:
            return
        if (
            logo_file.status.name != FileService.STATUS_AVAILABLE
            or logo_file.file_type != "image"
        ):
            raise BusinessPaymentService.ValidationError(
                {"logo_file_id": ["Select an available image file."]}
            )

    @staticmethod
    def validate_supported_methods(channel_code, methods):
        online = next((m for m in methods if m.code == "online"), None)
        if online and online.is_active:
            available, reason = provider_availability(channel_code)
            if not available:
                raise BusinessPaymentService.ValidationError(
                    {"payment_method_ids": [reason]}
                )

    @staticmethod
    def _generate_channel_code(base="", business=None):
        slug = (
            re.sub(
                r"[^A-Za-z0-9]+",
                "_",
                to_english_letters(base or ""),
            )
            .strip("_")
            .lower()[:80]
        )
        scope = (
            BusinessPaymentChannel.objects.filter(business=business)
            if business is not None
            else BusinessPaymentChannel.objects.all()
        )
        if slug and not scope.filter(code=slug).exists():
            return slug
        while True:
            candidate = (
                f"{slug}_{uuid4().hex[:6]}" if slug else f"channel_{uuid4().hex[:8]}"
            )[:100]
            if not scope.filter(code=candidate).exists():
                return candidate

    @transaction.atomic
    def create_channel(self, business, *, supported_methods, **values):
        self.validate_logo(values.get("logo_file"))
        code = (values.get("code") or "").strip()
        name = (values.get("name") or "").strip()
        fa_name = (values.get("fa_name") or "").strip()
        if not name and fa_name:
            name = to_english_letters(fa_name)
        if not code:
            code = self._generate_channel_code(name or fa_name, business=business)
        if not name:
            name = code
        values["code"] = code
        values["name"] = name
        values["business"] = business
        self.validate_supported_methods(values["code"], supported_methods)
        channel = BusinessPaymentChannel.objects.create(**values)
        BusinessPaymentChannelSupportedMethod.objects.bulk_create([
            BusinessPaymentChannelSupportedMethod(
                payment_channel=channel, payment_method=method
            )
            for method in supported_methods
        ])
        return self.get_channel(business, channel.id)

    @transaction.atomic
    def update_channel(self, business, channel, *, supported_methods=None, **values):
        if channel.payments.exists():
            if supported_methods is not None or set(values) - {"is_active"}:
                raise self.ValidationError({"payment_channel": [_(
                    "This channel has payments. Only its active status can be changed."
                )]})
        if "logo_file" in values:
            self.validate_logo(values.get("logo_file"))
        methods = supported_methods
        if methods is not None:
            self.validate_supported_methods(channel.code, methods)
        for field, value in values.items():
            setattr(channel, field, value)
        channel.save()
        if methods is not None:
            channel.supported_methods.all().delete()
            BusinessPaymentChannelSupportedMethod.objects.bulk_create([
                BusinessPaymentChannelSupportedMethod(
                    payment_channel=channel, payment_method=method
                )
                for method in methods
            ])
        return self.get_channel(business, channel.id)

    def get_channel(self, business, channel_id):
        try:
            return self.list_channels(business).get(id=channel_id)
        except BusinessPaymentChannel.DoesNotExist as exc:
            raise self.NotFoundError("Payment channel not found.") from exc

    @transaction.atomic
    def delete_channel(self, business, channel_id):
        channel = self.get_channel(business, channel_id)
        if channel.payments.exists():
            raise self.ValidationError(
                {"payment_channel": [_(
                    "This channel has payments and cannot be deleted."
                )]}
            )
        channel.delete()
        return channel

    def list_payments(
        self, business, *, search="", status=None, ordering="-created_at"
    ):
        queryset = BusinessPayment.objects.filter(
            business=business
        ).select_related("payment_method", "payment_channel", "order", "status")
        if search:
            queryset = queryset.filter(
                Q(ref_number__icontains=search)
                | Q(order__id__icontains=search)
            )
        if status is not None:
            queryset = queryset.filter(status__name=status)
        allowed_ordering = {
            "id", "amount", "status", "created_at", "updated_at",
            "payment_method__code",
        }
        if ordering.lstrip("-") not in allowed_ordering:
            ordering = "-created_at"
        return queryset.order_by(ordering, "-id")

    def get_payment(self, business, payment_id):
        try:
            return BusinessPayment.objects.select_related(
                "payment_method", "payment_channel", "order", "status"
            ).get(id=payment_id, business=business)
        except BusinessPayment.DoesNotExist as exc:
            raise self.NotFoundError("Payment not found.") from exc

    def payment_payload(self, payment):
        return {
            "id": payment.id,
            "business_id": payment.business_id,
            "order_id": payment.order_id,
            "payment_method": {
                "id": payment.payment_method.id,
                "code": payment.payment_method.code,
                "name": payment.payment_method.name,
                "fa_name": payment.payment_method.fa_name,
            },
            "payment_channel": (
                {
                    "id": payment.payment_channel.id,
                    "code": payment.payment_channel.code,
                    "name": payment.payment_channel.name,
                    "fa_name": payment.payment_channel.fa_name,
                }
                if payment.payment_channel
                else None
            ),
            "amount": str(payment.amount),
            "status": {
                "id": payment.status.id,
                "name": payment.status.name,
                "title": payment.status.title,
            },
            "ref_number": payment.ref_number,
            "resource_account_number": payment.resource_account_number,
            "extra_data": payment.extra_data,
            "created_at": payment.created_at.isoformat(),
            "updated_at": payment.updated_at.isoformat(),
        }

    def list_documents(self, business, payment_id):
        payment = self.get_payment(business, payment_id)
        return BusinessPaymentDocument.objects.filter(
            payment=payment
        ).select_related("file__status").order_by("id")

    def document_payload(self, document):
        try:
            url = FileService().url(document.file)
        except FileService.Error:
            url = None
        return {
            "id": document.id,
            "payment_id": document.payment_id,
            "file_id": str(document.file_id),
            "original_name": document.file.original_name,
            "content_type": document.file.content_type,
            "file_type": document.file.file_type,
            "size": document.file.size,
            "url": url,
            "created_at": document.created_at.isoformat(),
        }
