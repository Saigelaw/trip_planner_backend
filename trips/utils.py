import requests
import os
from datetime import timedelta, datetime
from django.conf import settings
import polyline


ORS_API_KEY = settings.ORS_API_KEY


def geocode_location(location_name):
    """
    Converts a location name into a longitude and latitude coordinate using ORS.
    """
    url = "https://api.openrouteservice.org/geocode/search"
    params = {
        "api_key": ORS_API_KEY,
        "text": location_name,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data["features"]:
            # ORS returns coordinates as [longitude, latitude]
            return tuple(data["features"][0]["geometry"]["coordinates"])

    except requests.exceptions.RequestException as e:
        print(f"Error geocoding location '{location_name}': {e}")
        raise ValueError(
            f"Could not geocode location '{location_name}'. Check your internet connection and API key."
        )

    return None


def get_route_from_openrouteservice(coordinates):
    """
    Fetches route data for a heavy vehicle from the Openrouteservice Directions API.
    """
    url = "https://api.openrouteservice.org/v2/directions/driving-hgv"
    headers = {
        "Accept": "application/json, application/geo+json",
        "Authorization": ORS_API_KEY,
    }

    payload = {
        "coordinates": coordinates,
        "profile": "driving-hgv",
        "options": {"avoid_features": ["ferries", "tollways"]},
        "extra_info": ["tollways"],
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

        response.raise_for_status()
        data = response.json()

        if data["routes"]:
            route = data["routes"][0]
            encoded_geometry = route["geometry"]
            decoded_coordinates = polyline.decode(encoded_geometry)

            return {
                "distance": route["summary"]["distance"],  # in meters
                "duration": route["summary"]["duration"],  # in seconds
                "geometry": decoded_coordinates,
                "legs": route["segments"],
            }

    except requests.exceptions.RequestException as e:
        print(f"Error getting route from ORS: {e}")
        raise ValueError(
            "Could not get a valid route. Check your API key and input locations."
        )

    return None


def calculate_trip_logistics(
    current_location, pickup_location, dropoff_location, current_cycle_used_hrs
):
    """
    Calculates the full trip plan, including rests, stops, and ELD log data.
    """
    # 1. Geocode all locations
    current_coords = geocode_location(current_location)
    pickup_coords = geocode_location(pickup_location)
    dropoff_coords = geocode_location(dropoff_location)

    # 2. Get route data for the full trip (current -> pickup -> dropoff)
    route_data = get_route_from_openrouteservice(
        [current_coords, pickup_coords, dropoff_coords]
    )

    total_duration_sec = route_data["duration"]
    total_distance_m = route_data["distance"]

    total_hours = total_duration_sec / 3600
    total_miles = total_distance_m / 1609.34

    # --- Assumptions and HOS Rules ---
    DAILY_DRIVING_LIMIT = 11.0  # 11 hours maximum
    DAILY_ON_DUTY_LIMIT = 14.0  # 14 hours total on duty
    DAILY_REST_PERIOD = 10.0  # 10 hours off duty required
    WEEKLY_CYCLE_LIMIT = 70.0  # 70 hours in an 8-day period
    PICKUP_DROPOFF_TIME = 1.0  # 1 hour for each
    FUELING_TIME = 0.5  # 30 minutes for fueling
    FUEL_STOP_MILEAGE = 1000  # Fueling every 1000 miles

    remaining_cycle_hours = WEEKLY_CYCLE_LIMIT - float(current_cycle_used_hrs)

    eld_logs = []
    current_time = datetime.now()

    # Simplify the trip into three main legs for calculation
    # Deadhead: current_location to pickup_location
    # Pickup: On duty, not driving
    # Loaded: pickup_location to dropoff_location
    # Dropoff: On duty, not driving

    # We must calculate the duration of each leg individually using ORS
    # This is a more complex but accurate approach. Let's simplify for now
    # and use the total route duration, subtracting non-driving time.

    total_driving_time = total_hours
    total_non_driving_on_duty = PICKUP_DROPOFF_TIME * 2

    time_remaining_in_day = DAILY_ON_DUTY_LIMIT
    hours_left_on_cycle = remaining_cycle_hours

    miles_covered = 0

    while total_driving_time > 0:
        # If not the first day, reset current_time to midnight of the next day
        if len(eld_logs) > 0:
            current_time = datetime.combine(
                current_time.date() + timedelta(days=1), datetime.min.time()
            )
        day_log = {"date": current_time.date().isoformat(), "events": []}

        # Start the day with a rest period, unless it's the very first day
        if len(eld_logs) > 0:
            # Alternate between 'off_duty' and 'sleeper_berth' for rest periods
            rest_type = "sleeper_berth" if len(eld_logs) % 2 == 1 else "off_duty"
            day_log["events"].append(
                {
                    "type": rest_type,
                    "start_time": current_time.isoformat(),
                    "duration": DAILY_REST_PERIOD,
                }
            )
            current_time += timedelta(hours=DAILY_REST_PERIOD)

        driving_hours_today = min(
            DAILY_DRIVING_LIMIT,
            time_remaining_in_day,
            total_driving_time,
            hours_left_on_cycle,
        )

        # Add a check for on-duty hours
        if len(eld_logs) == 0:
            # First day: Add pickup time
            pickup_event = {
                "type": "on_duty",
                "start_time": current_time.isoformat(),
                "duration": PICKUP_DROPOFF_TIME,
            }
            day_log["events"].append(pickup_event)
            current_time += timedelta(hours=PICKUP_DROPOFF_TIME)
            time_remaining_in_day -= PICKUP_DROPOFF_TIME
            hours_left_on_cycle -= PICKUP_DROPOFF_TIME

        # Add driving time
        driving_event = {
            "type": "driving",
            "start_time": current_time.isoformat(),
            "duration": driving_hours_today,
        }
        day_log["events"].append(driving_event)
        current_time += timedelta(hours=driving_hours_today)
        miles_covered += driving_hours_today * (total_miles / total_hours)

        # Check for fuel stop
        if (
            miles_covered >= FUEL_STOP_MILEAGE
            and (miles_covered - (driving_hours_today * (total_miles / total_hours)))
            < FUEL_STOP_MILEAGE
        ):
            fuel_event = {
                "type": "on_duty",
                "start_time": current_time.isoformat(),
                "duration": FUELING_TIME,
            }
            day_log["events"].append(fuel_event)
            current_time += timedelta(hours=FUELING_TIME)
            time_remaining_in_day -= FUELING_TIME
            hours_left_on_cycle -= FUELING_TIME

        total_driving_time -= driving_hours_today
        time_remaining_in_day -= driving_hours_today
        hours_left_on_cycle -= driving_hours_today

        # Add remaining on-duty time
        on_duty_duration = max(0, time_remaining_in_day)
        if on_duty_duration > 0:
            on_duty_event = {
                "type": "on_duty",
                "start_time": current_time.isoformat(),
                "duration": on_duty_duration,
            }
            day_log["events"].append(on_duty_event)
            current_time += timedelta(hours=on_duty_duration)

        # Only add off duty if there is idle time before the next required rest period
        # Calculate time until the next rest period (DAILY_REST_PERIOD)
        # If the next day starts with a rest period, do not add off_duty
        # Otherwise, add off_duty only if there is time left in the day and it's less than the rest period
        next_rest_starts_at_midnight = True
        if len(eld_logs) > 0:
            # If the next day starts with a rest period, don't add off_duty
            next_rest_starts_at_midnight = True
        else:
            next_rest_starts_at_midnight = False

        end_of_day = datetime.combine(current_time.date(), datetime.max.time())
        off_duty_duration = (end_of_day - current_time).total_seconds() / 3600
        # Only add off_duty if it's a reasonable duration (not a full day) and not immediately followed by a rest period
        if (
            off_duty_duration > 0
            and off_duty_duration < DAILY_REST_PERIOD
            and not next_rest_starts_at_midnight
        ):
            off_duty_event = {
                "type": "off_duty",
                "start_time": current_time.isoformat(),
                "duration": off_duty_duration,
            }
            day_log["events"].append(off_duty_event)
            current_time += timedelta(hours=off_duty_duration)

        eld_logs.append(day_log)
        time_remaining_in_day = DAILY_ON_DUTY_LIMIT

        # On the last day, add the dropoff time
        eld_logs[-1]["events"].append(
            {
                "type": "on_duty",
                "start_time": current_time.isoformat(),
                "duration": PICKUP_DROPOFF_TIME,
            }
        )

    return route_data, eld_logs
