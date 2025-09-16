import pytest
from rest_framework import status
from rest_framework.test import APIClient
from trips.models import Trip
from trips.utils import calculate_trip_logistics


@pytest.mark.django_db
def test_create_trip_api_success(mocker):
    """
    Test that the API endpoint successfully creates a new trip with calculated data.
    """
    client = APIClient()
    url = "/api/v1/trip_plan/"

    data = {
        "current_location": "New York, NY",
        "pickup_location": "New York, NY",
        "dropoff_location": "Chicago, IL",
        "current_cycle_used_hrs": 10.5,
    }

    # Mock the external API calls
    mocker.patch(
        "trip_planner.utils.geocode_location",
        side_effect=[
            (-74.0060, 40.7128),  # NYC
            (-74.0060, 40.7128),  # NYC
            (-87.6298, 41.8781),  # Chicago
        ],
    )

    # Mock the route data response from Openrouteservice
    mock_route_data = {
        "distance": 1931000,  # Approx. 1200 miles in meters
        "duration": 72000,  # 20 hours in seconds
        "geometry": [[-74.0060, 40.7128], [-87.6298, 41.8781]],
        "legs": [
            {"duration": 72000, "distance": 1931000},
        ],
    }
    mocker.patch(
        "trip_planner.utils.get_route_from_openrouteservice",
        return_value=mock_route_data,
    )

    response = client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert Trip.objects.count() == 1

    trip = Trip.objects.first()
    assert trip.pickup_location == "New York, NY"
    assert trip.dropoff_location == "Chicago, IL"

    # Check that the backend returned the calculated data
    assert "route_data" in response.data
    assert "eld_logs_data" in response.data
    assert isinstance(response.data["eld_logs_data"], list)
    assert len(response.data["eld_logs_data"]) > 0


def test_calculate_trip_logistics_function(mocker):
    """
    Test the standalone calculation utility function.
    """
    # Mock the geocoding and routing calls
    mocker.patch(
        "trip_planner.utils.geocode_location",
        side_effect=[
            (-74.0060, 40.7128),  # NYC
            (-74.0060, 40.7128),  # NYC
            (-87.6298, 41.8781),  # Chicago
        ],
    )

    mock_route_data = {
        "distance": 1931000,  # Approx. 1200 miles in meters
        "duration": 72000,  # 20 hours in seconds
        "geometry": [[-74.0060, 40.7128], [-87.6298, 41.8781]],
        "legs": [
            {"duration": 72000, "distance": 1931000},
        ],
    }
    mocker.patch(
        "trip_planner.utils.get_route_from_openrouteservice",
        return_value=mock_route_data,
    )

    current_location = "New York, NY"
    pickup_location = "New York, NY"
    dropoff_location = "Chicago, IL"
    current_cycle_used_hrs = 10.5

    route_data, eld_logs_data = calculate_trip_logistics(
        current_location, pickup_location, dropoff_location, current_cycle_used_hrs
    )

    assert "distance" in route_data
    assert "duration" in route_data
    assert "geometry" in route_data

    assert isinstance(eld_logs_data, list)
    assert len(eld_logs_data) > 0
    assert "date" in eld_logs_data[0]
    assert "events" in eld_logs_data[0]
