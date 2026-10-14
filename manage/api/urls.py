from django.urls import path

from .cow_views import CowDetailView, CowListCreateView
from .views import FarmListCreateView, FarmUpdateView

app_name = "manage"

urlpatterns = [
    path("farms/<uuid:farm_id>/cows/", CowListCreateView.as_view(), name="cow_list_create"),
    path("farms/<uuid:farm_id>/cows/<uuid:cow_id>/", CowDetailView.as_view(), name="cow_detail"),
    path("farms/", FarmListCreateView.as_view(), name="farm_create"),
    path("farms/<uuid:farm_id>/", FarmUpdateView.as_view(), name="farm_update"),
]
