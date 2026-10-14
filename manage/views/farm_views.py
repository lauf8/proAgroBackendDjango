from django.db.models import Prefetch, prefetch_related_objects
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, UpdateAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from accounts.models import FarmMembership
from manage.models import Farm
from manage.api.permissions import IsSuperUser, IsSuperUserOrFarmMember
from manage.serializers.farm_serializers import (
    FarmCreateSerializer,
    FarmDetailSerializer,
    FarmListQuerySerializer,
    FarmUpdateSerializer,
)


def owner_membership_prefetch():
    return Prefetch(
        "memberships",
        queryset=FarmMembership.objects.filter(
            role=FarmMembership.Role.OWNER, is_active=True,
        ).select_related("user").order_by("created_at", "id"),
        to_attr="active_owner_memberships",
    )


class FarmQuerysetMixin:
    def get_queryset(self):
        return Farm.objects.order_by("name", "id").prefetch_related(owner_membership_prefetch())


class FarmPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class FarmListCreateView(FarmQuerysetMixin, ListCreateAPIView):
    permission_classes = (IsSuperUser,)
    pagination_class = FarmPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return FarmCreateSerializer
        return FarmDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        query = FarmListQuerySerializer(data=self.request.query_params.dict())
        query.is_valid(raise_exception=True)
        if "is_active" in query.validated_data:
            queryset = queryset.filter(is_active=query.validated_data["is_active"])
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        farm = serializer.save()
        prefetch_related_objects([farm], owner_membership_prefetch())
        return Response(
            FarmDetailSerializer(farm, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class FarmUpdateView(FarmQuerysetMixin, UpdateAPIView):
    permission_classes = (IsSuperUserOrFarmMember,)
    serializer_class = FarmUpdateSerializer
    lookup_url_kwarg = "farm_id"

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        farm = self.get_object()
        serializer = self.get_serializer(farm, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(FarmDetailSerializer(farm, context=self.get_serializer_context()).data)
