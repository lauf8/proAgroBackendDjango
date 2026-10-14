from django.urls import path

from .views import FarmCreateView

app_name = "manage"

urlpatterns = [
    path("farms/", FarmCreateView.as_view(), name="farm_create"),
]
