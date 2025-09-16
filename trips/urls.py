from django.urls import path
from .views import TripPlannerAPIView

urlpatterns = [
    path("v1/trip_plan/", TripPlannerAPIView.as_view(), name="trip_plan"),
]
