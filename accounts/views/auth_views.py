from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView
from accounts.serializers.auth_serializers import EmailTokenObtainPairSerializer, PasswordChangeSerializer


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = (AllowAny,)


class RefreshView(TokenRefreshView):
    permission_classes = (AllowAny,)


class LogoutView(TokenBlacklistView):
    permission_classes = (AllowAny,)


class CurrentUserView(APIView):
    def get(self, request):
        return Response({
            "id": str(request.user.pk),
            "name": request.user.name,
            "email": request.user.email,
            "is_superuser": request.user.is_superuser,
        })


class PasswordChangeView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = PasswordChangeSerializer(
            instance=request.user, data=request.data, context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
