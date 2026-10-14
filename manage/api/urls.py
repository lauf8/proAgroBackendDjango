from django.urls import path

from .views import FarmListCreateView, FarmUpdateView

app_name = "manage"

urlpatterns = [
    path("farms/", FarmListCreateView.as_view(), name="farm_create"),
    path("farms/<uuid:farm_id>/", FarmUpdateView.as_view(), name="farm_update"),
]
