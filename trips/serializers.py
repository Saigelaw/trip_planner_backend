from rest_framework import serializers
from .models import Trip


class TripSerializer(serializers.ModelSerializer):
    """
    Serializer for the Trip model, handling both input and output.
    """

    class Meta:
        model = Trip
        fields = (
            "id",
            "current_location",
            "pickup_location",
            "dropoff_location",
            "current_cycle_used_hrs",
            "route_data",
            "eld_logs_data",
            "created_at",
        )
        read_only_fields = ("id", "route_data", "eld_logs_data", "created_at")
