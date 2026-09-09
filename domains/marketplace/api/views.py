from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from ..models import BusinessOffer
from .serializers import BusinessOfferSerializer


class BusinessOfferListCreate(APIView):
    authentication_classes = [AdminJWTAuthentication]

    def get(self, request):
        offers = BusinessOffer.objects.select_related("business", "variant").order_by("-created_at")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(offers, request, view=self)
        serializer = BusinessOfferSerializer(page, many=True)
        return api_response(True, "", paginator.get_paginated_response(serializer.data).data)

    def post(self, request):
        serializer = BusinessOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offer = BusinessOffer.objects.create(**serializer.validated_data)
        return api_response(
            True,
            "Created.",
            BusinessOfferSerializer(offer).data,
            status_code=status.HTTP_201_CREATED,
        )


class BusinessOfferDetail(APIView):
    authentication_classes = [AdminJWTAuthentication]

    def get(self, request, pk):
        offer = self._get(pk)
        return api_response(True, "", BusinessOfferSerializer(offer).data)

    def patch(self, request, pk):
        offer = self._get(pk)
        serializer = BusinessOfferSerializer(offer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for attr, value in serializer.validated_data.items():
            setattr(offer, attr, value)
        offer.save()
        return api_response(True, "Updated.", BusinessOfferSerializer(offer).data)

    def delete(self, request, pk):
        offer = self._get(pk)
        offer.delete()
        return api_response(True, "Deleted.")

    def _get(self, pk):
        from django.shortcuts import get_object_or_404

        return get_object_or_404(BusinessOffer, pk=pk)
