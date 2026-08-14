from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PaymentMigrationTests(TransactionTestCase):
    migrate_from = [
        ("payments", None),
        ("order", "0001_initial"),
        ("files", "0002_file_statuses"),
    ]
    migrate_to = [
        ("payments", "0002_refactor_payment_models"),
        ("order", "0002_transfer_payments_and_statuses"),
    ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state([
            target for target in self.migrate_from if target[1] is not None
        ]).apps

        OrderStatus = apps.get_model("order", "OrderStatus")
        CustomerStatus = apps.get_model("customer", "CustomerStatus")
        Customer = apps.get_model("customer", "Customer")
        Order = apps.get_model("order", "Order")
        Method = apps.get_model("order", "OrderPaymentMethod")
        Channel = apps.get_model("order", "OrderPaymentChannel")
        Support = apps.get_model("order", "OrderPaymentChannelSupportMethod")
        OldPayment = apps.get_model("order", "OrderPayment")

        paid_status, _ = OrderStatus.objects.update_or_create(
            id=2, defaults={"name": "success", "fa_name": "موفق"}
        )
        customer_status = CustomerStatus.objects.create(name="migration-active", title="Active")
        customer = Customer.objects.create(
            phone="09120000901", customer_code="CUS-MIG-001", status=customer_status,
            password="!", first_name="Migration", last_name="Test",
        )
        order = Order.objects.create(
            customer=customer, status=paid_status, address_info={}, subtotal="100.00",
            discount_amount="0.00", shipping_amount="0.00", total_amount="100.00",
        )
        method = Method.objects.create(name="card_to_card", fa_name="کارت", available=False)
        channel = Channel.objects.create(name="Legacy Channel", fa_name="قدیمی")
        Support.objects.create(payment_channel=channel, payment_method=method)
        payment = OldPayment.objects.create(
            order=order, payment_method=method, payment_channel=channel,
            amount="100.00", status="success",
        )
        order.successful_payment = payment
        order.save(update_fields=["successful_payment"])
        self.ids = {"order": order.id, "method": method.id, "channel": channel.id, "payment": payment.id}

        content_type, _ = ContentType.objects.get_or_create(
            app_label="order", model="orderpaymentmethod"
        )
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename="view_orderpaymentmethod",
            defaults={"name": "Can view order payment method"},
        )
        user = User.objects.create_user("migration-permission")
        user.user_permissions.add(permission)
        self.user_id = user.id
        self.permission_id = permission.id

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_rows_tables_statuses_and_permissions_are_preserved(self):
        Payment = self.apps.get_model("payments", "Payment")
        Method = self.apps.get_model("payments", "PaymentMethod")
        Channel = self.apps.get_model("payments", "PaymentChannel")
        Order = self.apps.get_model("order", "Order")

        payment = Payment.objects.get(id=self.ids["payment"])
        method = Method.objects.get(id=self.ids["method"])
        channel = Channel.objects.get(id=self.ids["channel"])
        order = Order.objects.get(id=self.ids["order"])
        self.assertEqual(payment.status, "successful")
        self.assertEqual(method.code, "card_to_card")
        self.assertEqual(method.name, "card_to_card")
        self.assertFalse(method.is_active)
        self.assertEqual(channel.name, "Legacy Channel")
        self.assertEqual(order.status.name, "paid")
        self.assertEqual(order.successful_payment_id, payment.id)
        self.assertEqual(Payment._meta.db_table, "shop_order_payment")

        permission = Permission.objects.get(id=self.permission_id)
        self.assertEqual(permission.content_type.app_label, "payments")
        self.assertEqual(permission.content_type.model, "paymentmethod")
        self.assertEqual(permission.codename, "view_paymentmethod")
        self.assertTrue(
            User.objects.get(id=self.user_id).user_permissions.filter(id=permission.id).exists()
        )


class InvalidPaymentMigrationTests(TransactionTestCase):
    migrate_from = PaymentMigrationTests.migrate_from
    migrate_to = PaymentMigrationTests.migrate_to

    def test_invalid_legacy_amount_fails_with_preflight_message(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state([
            target for target in self.migrate_from if target[1] is not None
        ]).apps

        OrderStatus = apps.get_model("order", "OrderStatus")
        CustomerStatus = apps.get_model("customer", "CustomerStatus")
        Customer = apps.get_model("customer", "Customer")
        Order = apps.get_model("order", "Order")
        Method = apps.get_model("order", "OrderPaymentMethod")
        Payment = apps.get_model("order", "OrderPayment")
        status, _ = OrderStatus.objects.get_or_create(
            name="payment_waiting", defaults={"fa_name": "Waiting"}
        )
        customer_status = CustomerStatus.objects.create(
            name="invalid-migration-active", title="Active"
        )
        customer = Customer.objects.create(
            phone="09120000902", customer_code="CUS-MIG-002",
            status=customer_status, password="!",
        )
        order = Order.objects.create(
            customer=customer, status=status, address_info={}, subtotal="1.00",
            discount_amount="0.00", shipping_amount="0.00", total_amount="1.00",
        )
        method = Method.objects.create(name="card_to_card", fa_name="Card")
        Payment.objects.create(
            order=order, payment_method=method, amount="0.00", status="pending"
        )

        with self.assertRaisesRegex(RuntimeError, "non-positive payment amount"):
            MigrationExecutor(connection).migrate(self.migrate_to)

        Payment.objects.all().delete()
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
