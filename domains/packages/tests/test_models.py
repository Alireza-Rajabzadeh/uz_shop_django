from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from domains.packages.models import Feature, Package, PackageFeature, PackagePriceHistory


class PackagePriceHistoryTests(TestCase):
    def setUp(self):
        self.package = Package.objects.create(
            code="growth", name="Growth", price=Decimal("100.00")
        )

    def test_creating_a_package_records_an_initial_history_row(self):
        history = list(self.package.price_history.all())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].price, Decimal("100.00"))
        self.assertEqual(history[0].off_discount, Decimal("0.00"))

    def test_changing_only_the_name_records_no_history(self):
        self.package.name = "Growth renamed"
        self.package.save()

        self.assertEqual(self.package.price_history.count(), 1)

    def test_toggling_is_active_records_no_history(self):
        self.package.is_active = False
        self.package.save()

        self.assertEqual(self.package.price_history.count(), 1)

    def test_changing_the_price_records_exactly_one_new_row(self):
        self.package.price = Decimal("150.00")
        self.package.save()

        prices = [row.price for row in self.package.price_history.all()]
        self.assertEqual(prices, [Decimal("100.00"), Decimal("150.00")])

    def test_changing_the_discount_records_exactly_one_new_row(self):
        self.package.off_discount = Decimal("25.00")
        self.package.save()

        discounts = [row.off_discount for row in self.package.price_history.all()]
        self.assertEqual(discounts, [Decimal("0.00"), Decimal("25.00")])

    def test_changing_price_and_discount_together_records_one_row_with_both(self):
        self.package.price = Decimal("200.00")
        self.package.off_discount = Decimal("10.00")
        self.package.save()

        history = list(self.package.price_history.all())
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1].price, Decimal("200.00"))
        self.assertEqual(history[1].off_discount, Decimal("10.00"))

    def test_saving_unchanged_pricing_records_no_history(self):
        self.package.save()
        self.package.save()

        self.assertEqual(self.package.price_history.count(), 1)

    def test_update_fields_without_pricing_records_no_history(self):
        self.package.name = "Growth renamed"
        self.package.save(update_fields=["name"])

        self.assertEqual(self.package.price_history.count(), 1)

    def test_history_rows_are_returned_chronologically(self):
        self.package.price = Decimal("150.00")
        self.package.save()
        self.package.price = Decimal("200.00")
        self.package.save()

        prices = [row.price for row in self.package.price_history.all()]
        self.assertEqual(
            prices, [Decimal("100.00"), Decimal("150.00"), Decimal("200.00")]
        )

    def test_rollback_discards_the_price_change_and_its_history(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.package.price = Decimal("999.00")
                self.package.save()
                raise RuntimeError("force rollback")

        self.package.refresh_from_db()
        self.assertEqual(self.package.price, Decimal("100.00"))
        self.assertEqual(self.package.price_history.count(), 1)

    def test_deleting_a_package_with_history_is_protected(self):
        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.package.delete()

        self.package.refresh_from_db()
        self.assertEqual(self.package.price_history.count(), 1)


class PackageConstraintTests(TestCase):
    def test_negative_price_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Package.objects.create(code="neg-price", name="Neg", price=Decimal("-1.00"))

    def test_discount_above_100_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Package.objects.create(
                    code="high-discount",
                    name="High",
                    price=Decimal("10.00"),
                    off_discount=Decimal("101.00"),
                )

    def test_negative_discount_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Package.objects.create(
                    code="neg-discount",
                    name="Neg",
                    price=Decimal("10.00"),
                    off_discount=Decimal("-1.00"),
                )

    def test_negative_price_is_rejected_by_model_validation(self):
        with self.assertRaises(ValidationError):
            Package(
                code="neg-price", name="Neg", price=Decimal("-1.00")
            ).full_clean()

    def test_discount_above_100_is_rejected_by_model_validation(self):
        with self.assertRaises(ValidationError):
            Package(
                code="high-discount",
                name="High",
                price=Decimal("10.00"),
                off_discount=Decimal("101.00"),
            ).full_clean()

    def test_valid_values_pass_model_validation(self):
        Package(
            code="valid", name="Valid", price=Decimal("10.00"), off_discount=Decimal("100.00")
        ).full_clean()

    def test_code_is_unique(self):
        Package.objects.create(code="taken", name="First", price=Decimal("1.00"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Package.objects.create(code="taken", name="Second", price=Decimal("2.00"))

    def test_package_code_cannot_change_after_creation(self):
        package = Package.objects.create(code="stable", name="Stable", price=Decimal("1.00"))
        package.code = "renamed"

        with self.assertRaises(ValidationError):
            package.save()

        package.refresh_from_db()
        self.assertEqual(package.code, "stable")

    def test_feature_code_cannot_change_after_creation(self):
        feature = Feature.objects.create(code="shop.products", name="Products")
        feature.code = "shop.items"

        with self.assertRaises(ValidationError):
            feature.save()

        feature.refresh_from_db()
        self.assertEqual(feature.code, "shop.products")


class PackageFeatureTests(TestCase):
    def setUp(self):
        self.package = Package.objects.create(
            code="growth", name="Growth", price=Decimal("100.00")
        )
        self.feature = Feature.objects.create(code="shop.products", name="Products")

    def test_duplicate_feature_assignment_is_rejected(self):
        PackageFeature.objects.create(package=self.package, feature=self.feature)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PackageFeature.objects.create(package=self.package, feature=self.feature)

    def test_the_same_feature_may_be_assigned_to_two_packages(self):
        other = Package.objects.create(code="pro", name="Pro", price=Decimal("200.00"))
        PackageFeature.objects.create(package=self.package, feature=self.feature)
        PackageFeature.objects.create(package=other, feature=self.feature)

        self.assertEqual(PackageFeature.objects.count(), 2)

    def test_config_default_is_not_shared_between_instances(self):
        first = PackageFeature(package=self.package, feature=self.feature)
        second = PackageFeature(
            package=self.package,
            feature=Feature.objects.create(code="shop.orders", name="Orders"),
        )

        self.assertIsNot(first.config, second.config)

        first.config["limit"] = 1000

        self.assertNotIn("limit", second.config)
        self.assertEqual(second.config, {})

    def test_stored_config_is_not_shared_between_rows(self):
        other_feature = Feature.objects.create(code="shop.orders", name="Orders")
        assigned = PackageFeature.objects.create(
            package=self.package, feature=self.feature, config={"enabled": True}
        )
        assigned_again = PackageFeature.objects.create(
            package=self.package, feature=other_feature, config={"enabled": True}
        )

        assigned.config["limit"] = 5
        assigned.save()

        assigned_again.refresh_from_db()
        self.assertNotIn("limit", assigned_again.config)

    def test_deleting_an_assigned_feature_is_protected(self):
        PackageFeature.objects.create(package=self.package, feature=self.feature)

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.feature.delete()

        self.feature.refresh_from_db()

    def test_deleting_a_package_removes_its_assignments(self):
        # History protects the package first, so clear it the way an operator
        # would have to, then confirm the assignment row still cascades.
        PackageFeature.objects.create(package=self.package, feature=self.feature)
        self.package.price_history.all().delete()

        self.package.delete()

        self.assertEqual(PackageFeature.objects.count(), 0)
