from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView
from .serializers import EmailTokenObtainPairSerializer


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
