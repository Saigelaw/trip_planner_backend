from django.db import models
from django.core.validators import MinValueValidator


class Trip(models.Model):
    """
    Represents a single truck trip with input details and calculated results.
    """

    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used_hrs = models.DecimalField(
        max_digits=4, decimal_places=2, validators=[MinValueValidator(0)]
    )

    # Fields to store the calculated results
    route_data = models.JSONField(default=dict)
    eld_logs_data = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trip from {self.pickup_location} to {self.dropoff_location}"
