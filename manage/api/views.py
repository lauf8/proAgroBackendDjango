from django.db.models import Prefetch, prefetch_related_objects
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.models import FarmMembership
from .permissions import IsSuperUser
from .serializers import FarmCreateSerializer, FarmDetailSerializer


class FarmCreateView(GenericAPIView):
    permission_classes = (IsSuperUser,)
    serializer_class = FarmCreateSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        farm = serializer.save()
        prefetch_related_objects(
            [farm],
            Prefetch(
                "memberships",
                queryset=FarmMembership.objects.filter(
                    role=FarmMembership.Role.OWNER, is_active=True,
                ).select_related("user").order_by("created_at", "id"),
                to_attr="active_owner_memberships",
            ),
        )
        return Response(
            FarmDetailSerializer(farm, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )
