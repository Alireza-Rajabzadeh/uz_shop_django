from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay
from domains.vendor.auth import VendorJWTAuthentication

from ..serializers.business import (
    VendorBusinessPhoneSerializer,
    VendorBusinessProfileSerializer,
    VendorBusinessSocialLinkSerializer,
    VendorBusinessWorkingDaySerializer,
)


def _get_business(request):
    return BusinessProfile.objects.filter(vendor=request.user).first()


class VendorBusinessProfileView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _get_business(request)
        if not profile:
            return api_response(data=None)
        return api_response(data=VendorBusinessProfileSerializer(profile).data)

    def post(self, request):
        if BusinessProfile.objects.filter(vendor=request.user).exists():
            return api_response(False, "Business profile already exists.", status_code=400)
        serializer = VendorBusinessProfileSerializer(data=request.data, context={"vendor": request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save(vendor=request.user)
        return api_response(data=serializer.data, status_code=201)

    def patch(self, request):
        profile = _get_business(request)
        if not profile:
            return api_response(False, "Business profile not found.", status_code=404)
        serializer = VendorBusinessProfileSerializer(profile, data=request.data, partial=True, context={"vendor": request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data)


class VendorBusinessPhoneListCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business = _get_business(request)
        if not business:
            return api_response(data=[])
        phones = BusinessPhone.objects.filter(business=business)
        return api_response(data=VendorBusinessPhoneSerializer(phones, many=True).data)

    def post(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)
        serializer = VendorBusinessPhoneSerializer(data=request.data, context={"business": business})
        serializer.is_valid(raise_exception=True)
        serializer.save(business=business)
        return api_response(data=serializer.data, status_code=201)


class VendorBusinessPhoneDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self):
        business = _get_business(self.request)
        return get_object_or_404(BusinessPhone, pk=self.kwargs["pk"], business=business)

    def get(self, request, pk):
        return api_response(data=VendorBusinessPhoneSerializer(self.get_object()).data)

    def patch(self, request, pk):
        obj = self.get_object()
        serializer = VendorBusinessPhoneSerializer(obj, data=request.data, partial=True, context={"business": obj.business})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data)

    def delete(self, request, pk):
        self.get_object().delete()
        return api_response()


class VendorBusinessSocialLinkListCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business = _get_business(request)
        if not business:
            return api_response(data=[])
        links = BusinessSocialLink.objects.filter(business=business).select_related("social_media", "icon__file__status")
        return api_response(data=VendorBusinessSocialLinkSerializer(links, many=True).data)

    def post(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)
        serializer = VendorBusinessSocialLinkSerializer(data=request.data, context={"business": business})
        serializer.is_valid(raise_exception=True)
        serializer.save(business=business)
        return api_response(data=serializer.data, status_code=201)


class VendorBusinessSocialLinkDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self):
        business = _get_business(self.request)
        return get_object_or_404(BusinessSocialLink, pk=self.kwargs["pk"], business=business)

    def get(self, request, pk):
        return api_response(data=VendorBusinessSocialLinkSerializer(self.get_object()).data)

    def patch(self, request, pk):
        obj = self.get_object()
        serializer = VendorBusinessSocialLinkSerializer(obj, data=request.data, partial=True, context={"business": obj.business})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data)

    def delete(self, request, pk):
        self.get_object().delete()
        return api_response()


class VendorBusinessWorkingDayListCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business = _get_business(request)
        if not business:
            return api_response(data=[])
        days = BusinessWorkingDay.objects.filter(vendor=request.user)
        return api_response(data=VendorBusinessWorkingDaySerializer(days, many=True).data)

    def post(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)
        serializer = VendorBusinessWorkingDaySerializer(data=request.data, context={"vendor": request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save(vendor=request.user)
        return api_response(data=serializer.data, status_code=201)


class VendorBusinessWorkingDayDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return get_object_or_404(BusinessWorkingDay, pk=self.kwargs["pk"], vendor=self.request.user)

    def get(self, request, pk):
        return api_response(data=VendorBusinessWorkingDaySerializer(self.get_object()).data)

    def patch(self, request, pk):
        serializer = VendorBusinessWorkingDaySerializer(self.get_object(), data=request.data, partial=True, context={"vendor": request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(data=serializer.data)

    def delete(self, request, pk):
        self.get_object().delete()
        return api_response()
