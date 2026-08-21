from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from core.services import CacheService
from domains.business.cache import BUSINESS_CACHE_KEY
from domains.business.models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay
from domains.business.services import BusinessService
from domains.users.auth import AdminJWTAuthentication

from .serializers import BusinessPhoneSerializer, BusinessProfileSerializer, BusinessSocialLinkSerializer, BusinessWorkingDaySerializer, PublicBusinessPhoneSerializer, PublicBusinessProfileSerializer, PublicBusinessSocialLinkSerializer, PublicBusinessWorkingDaySerializer


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
    def get_object(self, pk):
        return get_object_or_404(self.model, pk=pk)

    def get(self, request, pk):
        return api_response(data=self.serializer_class(self.get_object(pk)).data)

    def patch(self, request, pk):
        serializer = self.serializer_class(self.get_object(pk), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return api_response()


class PublicBusinessView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        cache = CacheService()
        cached = cache.get_public(BUSINESS_CACHE_KEY)
        if cached is not None:
            return api_response(data=cached)
        objects = BusinessService.public_data()
        profile = objects["profile"]
        data = {
            "profile": PublicBusinessProfileSerializer(profile).data if profile else None,
            "phones": PublicBusinessPhoneSerializer(objects["phones"], many=True).data,
            "social_links": PublicBusinessSocialLinkSerializer(objects["social_links"], many=True).data,
            "working_hours": PublicBusinessWorkingDaySerializer(objects["working_hours"], many=True).data,
        }
        if profile and profile.cache_ttl > 0:
            cache.put_public(BUSINESS_CACHE_KEY, data, ttl=profile.cache_ttl)
        return api_response(data=data)


class ProfileList(AdminBusinessListCreate):
    model, serializer_class = BusinessProfile, BusinessProfileSerializer
    search_fields = ("business_name", "display_name", "legal_name", "email")

class ProfileDetail(AdminBusinessDetail, ProfileList): pass

class PhoneList(AdminBusinessListCreate):
    model, serializer_class = BusinessPhone, BusinessPhoneSerializer
    search_fields = ("key", "title", "number", "extension")
    filter_fields = ("visibility", "status")
    ordering_fields = AdminBusinessBase.ordering_fields + ("position", "title", "key")

class PhoneDetail(AdminBusinessDetail, PhoneList): pass

class SocialLinkList(AdminBusinessListCreate):
    model, serializer_class = BusinessSocialLink, BusinessSocialLinkSerializer
    search_fields = ("key", "title", "platform", "url")
    filter_fields = ("visibility", "status", "platform")
    ordering_fields = AdminBusinessBase.ordering_fields + ("position", "title", "key", "platform")

class SocialLinkDetail(AdminBusinessDetail, SocialLinkList): pass

class WorkingDayList(AdminBusinessListCreate):
    model, serializer_class = BusinessWorkingDay, BusinessWorkingDaySerializer
    search_fields = ("description",)
    filter_fields = ("weekday", "is_open")
    ordering_fields = AdminBusinessBase.ordering_fields + ("weekday",)

class WorkingDayDetail(AdminBusinessDetail, WorkingDayList): pass
