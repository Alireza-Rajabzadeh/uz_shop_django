from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessCategory, BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay
from domains.vendor.auth import VendorJWTAuthentication

from ..serializers.business import (
    VendorBusinessPhoneSerializer,
    VendorBusinessProfileSerializer,
    VendorBusinessSocialLinkSerializer,
    VendorBusinessWorkingDaySerializer,
    VendorBusinessWorkingDayUpsertSerializer,
    VendorPhoneReorderSerializer,
    VendorSocialLinkReorderSerializer,
)
from domains.business.api.serializers import BusinessCategorySerializer, BusinessCategoryUpsertSerializer, CategoryBrowseSerializer


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


class VendorBusinessSocialLinkReorderView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)

        serializer = VendorSocialLinkReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data["social_links"]

        links = list(
            BusinessSocialLink.objects.select_for_update(of=("self",))
            .filter(business=business)
            .order_by("position", "id")
        )
        existing_ids = {link.id for link in links}

        if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != existing_ids:
            return api_response(
                False,
                "Provide every social link exactly once.",
                status_code=400,
            )

        by_id = {link.id: link for link in links}
        ordered = [by_id[link_id] for link_id in ordered_ids]
        updated_at = timezone.now()
        for position, link in enumerate(ordered):
            link.position = position
            link.updated_at = updated_at
        BusinessSocialLink.objects.bulk_update(ordered, ["position", "updated_at"])

        links_qs = BusinessSocialLink.objects.filter(business=business).select_related(
            "social_media", "icon__file__status"
        )
        return api_response(
            True,
            "Social links reordered.",
            VendorBusinessSocialLinkSerializer(links_qs, many=True).data,
        )


class VendorBusinessPhoneReorderView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)

        serializer = VendorPhoneReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data["phones"]

        phones = list(
            BusinessPhone.objects.select_for_update(of=("self",))
            .filter(business=business)
            .order_by("position", "id")
        )
        existing_ids = {phone.id for phone in phones}

        if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != existing_ids:
            return api_response(
                False,
                "Provide every phone exactly once.",
                status_code=400,
            )

        by_id = {phone.id: phone for phone in phones}
        ordered = [by_id[phone_id] for phone_id in ordered_ids]
        updated_at = timezone.now()
        for position, phone in enumerate(ordered):
            phone.position = position
            phone.updated_at = updated_at
        BusinessPhone.objects.bulk_update(ordered, ["position", "updated_at"])

        phones_qs = BusinessPhone.objects.filter(business=business)
        return api_response(
            True,
            "Phones reordered.",
            VendorBusinessPhoneSerializer(phones_qs, many=True).data,
        )


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


class VendorBusinessWorkingDayUpsertView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)

        serializer = VendorBusinessWorkingDayUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        day, _created = BusinessWorkingDay.objects.select_for_update().get_or_create(
            vendor=request.user,
            weekday=data["weekday"],
            defaults={
                "is_open": data["is_open"],
                "opens_at": data.get("opens_at"),
                "closes_at": data.get("closes_at"),
                "second_opens_at": data.get("second_opens_at"),
                "second_closes_at": data.get("second_closes_at"),
                "description": data.get("description", ""),
            },
        )
        if not _created:
            day.is_open = data["is_open"]
            day.opens_at = data.get("opens_at")
            day.closes_at = data.get("closes_at")
            day.second_opens_at = data.get("second_opens_at")
            day.second_closes_at = data.get("second_closes_at")
            day.description = data.get("description", "")
            day.save()

        days = BusinessWorkingDay.objects.filter(vendor=request.user)
        return api_response(
            data=VendorBusinessWorkingDaySerializer(days, many=True).data,
        )


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


class VendorBusinessDashboardView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _get_business(request)
        working_days = BusinessWorkingDay.objects.filter(vendor=request.user).order_by("weekday") if profile else []
        return api_response(data={
            "profile": VendorBusinessProfileSerializer(profile).data if profile else None,
            "working_days": VendorBusinessWorkingDaySerializer(working_days, many=True).data,
        })


class VendorBusinessCategoryView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Exists, OuterRef, Q
        from domains.catalog.models import Category

        business = _get_business(request)
        parent_id = request.query_params.get("parent")

        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except (TypeError, ValueError):
                return api_response(False, "Invalid parent id.", status_code=400)
            queryset = Category.objects.filter(parent_id=parent_id)
        else:
            queryset = Category.objects.filter(parent__isnull=True)

        queryset = queryset.order_by("name")

        selected_ids = set()
        if business:
            selected_ids = set(
                BusinessCategory.objects.filter(business=business)
                .values_list("category_id", flat=True)
            )

        categories = []
        for cat in queryset:
            categories.append({
                "id": cat.id,
                "name": cat.name,
                "fa_name": cat.fa_name,
                "slug": cat.slug,
                "has_children": cat.children.exists(),
                "selected": cat.id in selected_ids,
            })

        return api_response(data=CategoryBrowseSerializer(categories, many=True).data)


class VendorCategorySearchView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        from domains.catalog.models import Category

        q = request.query_params.get("q", "").strip()
        if not q:
            return api_response(data=[])

        categories = Category.objects.filter(
            Q(name__icontains=q) | Q(fa_name__icontains=q)
        ).select_related("parent").order_by("name")[:50]

        category_map = {c.id: c for c in categories}
        results = []
        for cat in categories:
            path_parts = [cat.name]
            parent_id = cat.parent_id
            seen = {cat.id}
            while parent_id and parent_id not in seen:
                seen.add(parent_id)
                parent = category_map.get(parent_id)
                if not parent:
                    parent = Category.objects.filter(id=parent_id).select_related("parent").first()
                    if parent:
                        category_map[parent.id] = parent
                if not parent:
                    break
                path_parts.append(parent.name)
                parent_id = parent.parent_id
            results.append({
                "id": cat.id,
                "name": cat.name,
                "fa_name": cat.fa_name,
                "slug": cat.slug,
                "path": " / ".join(reversed(path_parts)),
            })

        return api_response(data=results)

    @transaction.atomic
    def put(self, request):
        business = _get_business(request)
        if not business:
            return api_response(False, "Business profile not found.", status_code=400)

        serializer = BusinessCategoryUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category_ids = serializer.validated_data["category_ids"]

        existing_ids = set(
            BusinessCategory.objects.filter(business=business)
            .values_list("category_id", flat=True)
        )
        new_ids = set(category_ids)

        to_remove = existing_ids - new_ids
        to_add = new_ids - existing_ids

        if to_remove:
            BusinessCategory.objects.filter(business=business, category_id__in=to_remove).delete()

        if to_add:
            BusinessCategory.objects.bulk_create([
                BusinessCategory(business=business, category_id=cid)
                for cid in to_add
            ])

        categories = BusinessCategory.objects.filter(business=business).select_related("category")
        return api_response(data=BusinessCategorySerializer(categories, many=True).data)
