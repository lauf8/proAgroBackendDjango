from django.urls import path
from .views.auth_views import CurrentUserView, LoginView, LogoutView, PasswordChangeView, RefreshView

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("change-password/", PasswordChangeView.as_view(), name="change_password"),
    path("me/", CurrentUserView.as_view(), name="current_user"),
]
