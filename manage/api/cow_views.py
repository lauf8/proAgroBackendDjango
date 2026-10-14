from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from manage.models import Cow, Farm
from manage.services.cow_service import delete_cow
from .cow_serializers import CowDetailSerializer, CowListQuerySerializer, CowWriteSerializer
from .permissions import IsSuperUserOrFarmMember


class CowDeletionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This cow has related records and cannot be deleted."
    default_code = "cow_has_related_records"


class CowPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CowFarmScopeMixin:
    permission_classes = (IsSuperUserOrFarmMember,)

    @cached_property
    def farm(self):
        farm = get_object_or_404(Farm, pk=self.kwargs["farm_id"])
        self.check_object_permissions(self.request, farm)
        return farm

    def get_queryset(self):
        return Cow.objects.filter(farm=self.farm).order_by("name", "id")

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["cow_id"])

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "farm": self.farm}

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CowDetailSerializer
        return CowWriteSerializer


class CowListCreateView(CowFarmScopeMixin, ListCreateAPIView):
    pagination_class = CowPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        query = CowListQuerySerializer(data=self.request.query_params.dict())
        query.is_valid(raise_exception=True)
        if "status" in query.validated_data:
            queryset = queryset.filter(status=query.validated_data["status"])
        search = query.validated_data.get("search", "")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(identifier__icontains=search))
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cow = serializer.save()
        return Response(
            CowDetailSerializer(cow, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class CowDetailView(CowFarmScopeMixin, RetrieveUpdateDestroyAPIView):
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        cow = serializer.save()
        return Response(CowDetailSerializer(cow, context=self.get_serializer_context()).data)

    def perform_destroy(self, instance):
        try:
            delete_cow(cow=instance)
        except ProtectedError as error:
            raise CowDeletionConflict() from error
