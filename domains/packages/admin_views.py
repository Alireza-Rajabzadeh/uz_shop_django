from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import Feature, Package, PackageFeature
from .serializers import (
    FeatureCreateSerializer,
    FeatureSerializer,
    FeatureUpdateSerializer,
    PackageCreateSerializer,
    PackageFeatureAssignSerializer,
    PackageFeatureConfigSerializer,
    PackageFeatureSerializer,
    PackagePriceHistorySerializer,
    PackageSerializer,
    PackageUpdateSerializer,
)
from .services import PackageService


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


def _paginated(queryset, request, view, serializer_class):
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    data = serializer_class(page, many=True).data
    return api_response(True, "", paginator.get_paginated_response(data).data)


def _not_found(exc):
    return NotFound(next(iter(exc.errors.values()))[0])


class AdminPackageList(AdminAPIView):
    model = Package

    def get(self, request):
        return _paginated(
            PackageService.list_packages(), request, self, PackageSerializer
        )

    def post(self, request):
        serializer = PackageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = PackageService.create_package(**serializer.validated_data)
        return api_response(
            True,
            _("Package created."),
            PackageSerializer(package).data,
            status_code=201,
        )


class AdminPackageDetail(AdminAPIView):
    model = Package

    def get(self, request, package_id):
        try:
            package = PackageService.get_package(package_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc
        return api_response(True, "", PackageSerializer(package).data)

    def patch(self, request, package_id):
        try:
            package = PackageService.get_package(package_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc

        serializer = PackageUpdateSerializer(package, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        package = PackageService.update_package(package, **serializer.validated_data)
        return api_response(True, _("Package updated."), PackageSerializer(package).data)


class AdminPackagePriceHistory(AdminAPIView):
    model = Package

    def get(self, request, package_id):
        try:
            package = PackageService.get_package(package_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc
        # The model orders oldest-first, so the trail reads chronologically
        # and the newest row is the package's current pricing.
        return _paginated(
            PackageService.price_history(package),
            request,
            self,
            PackagePriceHistorySerializer,
        )


class AdminFeatureList(AdminAPIView):
    model = Feature

    def get(self, request):
        return _paginated(
            PackageService.list_features(), request, self, FeatureSerializer
        )

    def post(self, request):
        serializer = FeatureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feature = PackageService.create_feature(**serializer.validated_data)
        return api_response(
            True,
            _("Feature created."),
            FeatureSerializer(feature).data,
            status_code=201,
        )


class AdminFeatureDetail(AdminAPIView):
    model = Feature

    def get(self, request, feature_id):
        try:
            feature = PackageService.get_feature(feature_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc
        return api_response(True, "", FeatureSerializer(feature).data)

    def patch(self, request, feature_id):
        try:
            feature = PackageService.get_feature(feature_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc

        serializer = FeatureUpdateSerializer(feature, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        feature = PackageService.update_feature(feature, **serializer.validated_data)
        return api_response(True, _("Feature updated."), FeatureSerializer(feature).data)


class AdminPackageFeatureList(AdminAPIView):
    model = PackageFeature

    def _package(self, package_id):
        try:
            return PackageService.get_package(package_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc

    def get(self, request, package_id):
        package = self._package(package_id)
        items = PackageService.list_package_features(package)
        return _paginated(items, request, self, PackageFeatureSerializer)

    def post(self, request, package_id):
        package = self._package(package_id)
        serializer = PackageFeatureAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feature = serializer.validated_data["feature"]
        config = serializer.validated_data.get("config") or {}
        try:
            PackageService.assign_feature(package, feature, config)
        except PackageService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        assigned = PackageService.get_package_feature(package, feature.id)
        return api_response(
            True,
            _("Feature assigned."),
            PackageFeatureSerializer(assigned).data,
            status_code=201,
        )


class AdminPackageFeatureDetail(AdminAPIView):
    model = PackageFeature

    def _assignment(self, package_id, feature_id):
        try:
            package = PackageService.get_package(package_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc
        try:
            return PackageService.get_package_feature(package, feature_id)
        except PackageService.ValidationError as exc:
            raise _not_found(exc) from exc

    def patch(self, request, package_id, feature_id):
        assignment = self._assignment(package_id, feature_id)
        serializer = PackageFeatureConfigSerializer(
            assignment, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        assignment = PackageService.update_feature_config(
            assignment, **serializer.validated_data
        )
        return api_response(
            True,
            _("Feature configuration updated."),
            PackageFeatureSerializer(assignment).data,
        )

    def delete(self, request, package_id, feature_id):
        assignment = self._assignment(package_id, feature_id)
        PackageService.remove_feature(assignment)
        return api_response(True, _("Feature removed from package."), None)
