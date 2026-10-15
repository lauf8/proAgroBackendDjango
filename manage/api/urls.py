from django.urls import path

from manage.views.cow_views import CowDetailView, CowListCreateView
from manage.views.farm_views import FarmListCreateView, FarmUpdateView, FarmOptionsView

app_name = "manage"

urlpatterns = [
    path("farm-options/", FarmOptionsView.as_view(), name="farm_options"),
    path("farms/<uuid:farm_id>/cows/", CowListCreateView.as_view(), name="cow_list_create"),
    path("farms/<uuid:farm_id>/cows/<uuid:cow_id>/", CowDetailView.as_view(), name="cow_detail"),
    path("farms/", FarmListCreateView.as_view(), name="farm_create"),
    path("farms/<uuid:farm_id>/", FarmUpdateView.as_view(), name="farm_update"),
]
