from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import TripSerializer
from .utils import calculate_trip_logistics


class TripPlannerAPIView(APIView):
    """
    API view to receive trip details and return calculated route and ELD logs.
    """

    serializer_class = TripSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            # Extract input data from the validated serializer
            current_location = serializer.validated_data["current_location"]
            pickup_location = serializer.validated_data["pickup_location"]
            dropoff_location = serializer.validated_data["dropoff_location"]
            current_cycle_used_hrs = serializer.validated_data["current_cycle_used_hrs"]

            # Call the utility function to perform the complex calculations
            # The calculation function will be defined in the next step
            try:
                route_data, eld_logs_data = calculate_trip_logistics(
                    current_location,
                    pickup_location,
                    dropoff_location,
                    current_cycle_used_hrs,
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # Create and save the new Trip instance
            # The serializer handles the creation for us
            serializer.save(route_data=route_data, eld_logs_data=eld_logs_data)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
