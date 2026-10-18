from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from django.db import transaction

from core.permissions import AdminModelPermissions
from core.responses import api_response
from core.services import CacheService
from domains.business.cache import BUSINESS_CACHE_KEY
from domains.business.models import BusinessCategory, BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay, SocialMedia, SocialMediaIcon
from domains.business.services import BusinessService
from domains.users.auth import AdminJWTAuthentication

from .serializers import (
    BusinessCategorySerializer, BusinessCategoryUpsertSerializer,
    BusinessPhoneSerializer, BusinessProfileSerializer, BusinessSocialLinkSerializer,
    BusinessWorkingDaySerializer, PublicBusinessPhoneSerializer, PublicBusinessProfileSerializer,
    PublicBusinessSocialLinkSerializer, PublicBusinessWorkingDaySerializer, PublicSocialMediaSerializer,
    SocialMediaIconSerializer, SocialMediaSerializer,
)


class AdminBusinessBase(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]
    model = None
    serializer_class = None
    search_fields = ()
    filter_fields = ()
    ordering_fields = ("id", "created_at", "updated_at")

    def queryset(self, request):
        queryset = self.model.objects.all()
        if self.model is BusinessSocialLink:
            queryset = queryset.select_related("logo_file__status")
        search = request.query_params.get("search")
        if search and self.search_fields:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)
        for field in self.filter_fields:
            if field in request.query_params:
                queryset = queryset.filter(**{field: request.query_params[field]})
        ordering = request.query_params.get("ordering")
        if ordering and ordering.lstrip("-") in self.ordering_fields:
            queryset = queryset.order_by(ordering)
        return queryset


class AdminBusinessListCreate(AdminBusinessBase):
    def get(self, request):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(self.queryset(request), request, view=self)
        return api_response(data=paginator.get_paginated_response(self.serializer_class(page, many=True).data).data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data, status_code=201)


class AdminBusinessDetail(AdminBusinessBase):
    """Read and partial-update one row.

    Deleting is opted into separately: a business profile is the record a
    vendor's business *is*, so it deliberately has no delete, while the rows
    hanging off it keep theirs.
    """

    def get_object(self, pk):
        return get_object_or_404(self.model, pk=pk)

    def get(self, request, pk):
        return api_response(data=self.serializer_class(self.get_object(pk)).data)

    def patch(self, request, pk):
        serializer = self.serializer_class(self.get_object(pk), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data)


class AdminBusinessDetailDeletable(AdminBusinessDetail):
    """A detail view whose row may be removed outright."""

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return api_response()


class PublicBusinessView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def resolve_payload(self):
        """Return the public business payload and its cache TTL.

        A business without a profile is still a valid response, but there
        is no `cache_ttl` to honour, so nothing is stored.
        """
        objects = BusinessService.public_data()
        profile = objects["profile"]
        data = {
            "profile": PublicBusinessProfileSerializer(profile).data if profile else None,
            "phones": PublicBusinessPhoneSerializer(objects["phones"], many=True).data,
            "social_links": PublicBusinessSocialLinkSerializer(objects["social_links"], many=True).data,
            "working_hours": PublicBusinessWorkingDaySerializer(objects["working_hours"], many=True).data,
        }
        return data, (profile.cache_ttl if profile else None)

    def get(self, request):
        cache = CacheService()
        cached = cache.get_public(BUSINESS_CACHE_KEY)
        if cached is not None:
            return api_response(data=cached)
        data = cache.get_or_set_public(BUSINESS_CACHE_KEY, self.resolve_payload)
        return api_response(data=data)


class PublicSocialMediaListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        social_medias = SocialMedia.objects.filter(is_active=True).prefetch_related("icons__file__status")
        return api_response(data=PublicSocialMediaSerializer(social_medias, many=True).data)


class ProfileList(AdminBusinessListCreate):
    model, serializer_class = BusinessProfile, BusinessProfileSerializer
    search_fields = ("business_name", "display_name", "legal_name", "email")

class ProfileDetail(AdminBusinessDetail, ProfileList):
    """A business profile is never deleted: it is the vendor's business.

    Ban or retire a business by moving its status instead.
    """

class PhoneList(AdminBusinessListCreate):
    model, serializer_class = BusinessPhone, BusinessPhoneSerializer
    search_fields = ("key", "title", "number", "extension")
    filter_fields = ("visibility", "status")
    ordering_fields = AdminBusinessBase.ordering_fields + ("position", "title", "key")

class PhoneDetail(AdminBusinessDetailDeletable, PhoneList): pass

class SocialLinkList(AdminBusinessListCreate):
    model, serializer_class = BusinessSocialLink, BusinessSocialLinkSerializer
    search_fields = ("key", "title", "url")
    filter_fields = ("visibility", "status")
    ordering_fields = AdminBusinessBase.ordering_fields + ("position", "title", "key")

    def queryset(self, request):
        queryset = super().queryset(request)
        return queryset.select_related("social_media", "icon__file__status")


class SocialLinkDetail(AdminBusinessDetailDeletable, SocialLinkList): pass


class SocialMediaList(AdminBusinessListCreate):
    model, serializer_class = SocialMedia, SocialMediaSerializer
    search_fields = ("name", "fa_name", "slug")
    filter_fields = ("is_active",)
    ordering_fields = AdminBusinessBase.ordering_fields + ("position", "name", "slug")

    def queryset(self, request):
        queryset = super().queryset(request)
        return queryset.prefetch_related("icons__file__status")


class SocialMediaDetail(AdminBusinessDetailDeletable, SocialMediaList): pass


class SocialMediaIconList(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]
    model = SocialMediaIcon

    def post(self, request, pk):
        social_media = get_object_or_404(SocialMedia, pk=pk)
        serializer = SocialMediaIconSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(social_media=social_media)
        return api_response(data=serializer.data, status_code=201)


class SocialMediaIconDetail(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]
    model = SocialMediaIcon

    def delete(self, request, pk, icon_pk):
        icon = get_object_or_404(SocialMediaIcon, pk=icon_pk, social_media_id=pk)
        icon.delete()
        return api_response()


class WorkingDayList(AdminBusinessListCreate):
    model, serializer_class = BusinessWorkingDay, BusinessWorkingDaySerializer
    search_fields = ("description",)
    filter_fields = ("weekday", "is_open")
    ordering_fields = AdminBusinessBase.ordering_fields + ("weekday",)

class WorkingDayDetail(AdminBusinessDetailDeletable, WorkingDayList): pass


class AdminBusinessProfileCategoryView(APIView):
    """The catalog categories one business profile is registered under.

    Only root categories may be registered, and PUT replaces the whole set.
    The rows always belonged to a profile; the route names the one to read or
    replace instead of assuming the first profile in the table.
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]
    model = BusinessCategory

    def get(self, request, pk):
        business = get_object_or_404(BusinessProfile, pk=pk)
        return api_response(
            data=BusinessCategorySerializer(BusinessService.profile_categories(business), many=True).data
        )

    def put(self, request, pk):
        business = get_object_or_404(BusinessProfile, pk=pk)
        serializer = BusinessCategoryUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        categories = BusinessService.replace_profile_categories(
            business, serializer.validated_data["category_ids"]
        )
        return api_response(data=BusinessCategorySerializer(categories, many=True).data)
