from rest_framework import serializers
from rest_framework.reverse import reverse
from celery.result import AsyncResult
from taggit.serializers import TaggitSerializer, TagListSerializerField

from .models import EnvironmentMesh, VehicleMesh, Vehicle, Route, Job, Location
from polarrouteserver.celery import app
from polarrouteserver._version import __version__ as polarrouteserver_version


class JobStatusSerializer(serializers.ModelSerializer):
    """
    Serializer for job status responses with dynamic status and route URL.

    The status field returns Celery task states:
    - PENDING: Task is waiting for execution or unknown task id
    - STARTED: Task has been started
    - SUCCESS: Task executed successfully
    - FAILURE: Task failed with an exception
    - RETRY: Task is being retried after failure
    - REVOKED: Task was revoked/cancelled
    """

    status = serializers.SerializerMethodField()
    route_url = serializers.SerializerMethodField()
    info = serializers.SerializerMethodField()
    route_id = serializers.CharField(source="route.id", read_only=True)
    created = serializers.DateTimeField(source="datetime", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "status",
            "route_id",
            "created",
            "route_url",
            "info",
        ]

    def _get_celery_result(self, obj):
        """Get Celery result object for this job."""
        if not hasattr(self, "_celery_result_cache"):
            self._celery_result_cache = {}

        if obj.id not in self._celery_result_cache:
            self._celery_result_cache[obj.id] = AsyncResult(id=str(obj.id), app=app)

        return self._celery_result_cache[obj.id]

    def get_status(self, obj):
        """Get current job status from Celery."""
        result = self._get_celery_result(obj)
        return result.state

    def get_route_url(self, obj):
        """Include route URL when job is successful."""
        result = self._get_celery_result(obj)
        if result.state == "SUCCESS":
            request = self.context.get("request")
            if request:
                return reverse("route_detail", args=[obj.route.id], request=request)
        return None

    def get_info(self, obj):
        """Include error info when job failed."""
        result = self._get_celery_result(obj)
        if result.state == "FAILURE":
            return obj.route.info
        return None

    def to_representation(self, instance):
        """Add version to response."""
        data = super().to_representation(instance)
        data["polarrouteserver-version"] = polarrouteserver_version

        # Remove None values for cleaner response
        return {k: v for k, v in data.items() if v is not None}


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "vessel_type",
            "max_speed",
            "unit",
            "max_ice_conc",
            "min_depth",
            "max_wave",
            "excluded_zones",
            "neighbour_splitting",
            "beam",
            "hull_type",
            "force_limit",
        ]


class VesselTypeSerializer(serializers.Serializer):
    class Meta:
        vessel_type = serializers.CharField()


class RouteSerializer(TaggitSerializer, serializers.ModelSerializer):
    tags = TagListSerializerField()

    class Meta:
        model = Route
        fields = [
            "id",
            "start_lat",
            "start_lon",
            "end_lat",
            "end_lon",
            "start_name",
            "end_name",
            "json",
            "json_unsmoothed",
            "polar_route_version",
            "info",
            "mesh",
            "requested",
            "calculated",
            "tags",
        ]

    def _extract_routes_by_type(self, route_data, route_type):
        """Extract routes of a specific optimisation type from route data."""
        if route_data is None:
            return []

        return [
            x
            for x in route_data
            if (
                x
                and len(x) > 0
                and isinstance(x[0], dict)
                and x[0].get("features")
                and len(x[0]["features"]) > 0
                and x[0]["features"][0].get("properties", {}).get("objective_function")
                == route_type
            )
        ]

    def _build_optimisation_metrics(self, route_type, properties):
        """Build all available metrics from route properties."""
        metrics = {}

        total_traveltime = properties.get("total_traveltime")
        if total_traveltime is not None:
            metrics["time"] = {"duration": str(total_traveltime)}

        # Handle energy consumption with consistent structure
        total_fuel = properties.get("total_fuel")
        total_battery = properties.get("total_battery")

        if total_fuel is not None:
            metrics["energyConsumption"] = {
                "value": total_fuel,
                "units": properties.get("fuel_units") or "tons",
                "source": "fuel",
            }
        elif total_battery is not None:
            metrics["energyConsumption"] = {
                "value": total_battery,
                "units": properties.get("battery_units") or "Ah / day",
                "source": "battery",
            }

        distance_data = properties.get("distance")
        if distance_data and isinstance(distance_data, list) and len(distance_data) > 0:
            # Take the last value which should be the total distance
            total_distance = distance_data[-1]
            metrics["distance"] = {"value": total_distance, "units": "meters"}

        return metrics

    def _build_mesh_info(self, instance):
        """Build mesh information from the route instance."""
        if not instance.mesh:
            return None

        return {
            "id": instance.mesh.id,
            "name": instance.mesh.name,
            "validDateStart": instance.mesh.valid_date_start.isoformat()
            if instance.mesh.valid_date_start
            else None,
            "validDateEnd": instance.mesh.valid_date_end.isoformat()
            if instance.mesh.valid_date_end
            else None,
            "bounds": {
                "latMin": instance.mesh.lat_min,
                "latMax": instance.mesh.lat_max,
                "lonMin": instance.mesh.lon_min,
                "lonMax": instance.mesh.lon_max,
            },
        }

    def _build_vehicle_info(self, instance):
        """Build vehicle information from the route instance."""
        if not instance.vehicle:
            return None

        vehicle_data = {
            "vessel_type": instance.vehicle.vessel_type,
            "max_speed": instance.vehicle.max_speed,
            "unit": instance.vehicle.unit,
        }

        # Add optional fields if they exist
        optional_fields = [
            "max_ice_conc",
            "min_depth",
            "max_wave",
            "excluded_zones",
            "neighbour_splitting",
            "beam",
            "hull_type",
            "force_limit",
        ]

        for field in optional_fields:
            value = getattr(instance.vehicle, field, None)
            if value is not None:
                vehicle_data[field] = value

        return vehicle_data

    def to_representation(self, instance):
        """Transform route data into structured format."""
        data = super().to_representation(instance)

        # Extract and organise route data by optimisation type
        smoothed_routes = {}
        unsmoothed_routes = {}

        # Support both fuel and battery energy sources
        supported_route_types = ("traveltime", "fuel", "battery")

        for route_type in supported_route_types:
            smoothed_routes[route_type] = self._extract_routes_by_type(
                data["json"], route_type
            )
            unsmoothed_routes[route_type] = self._extract_routes_by_type(
                data["json_unsmoothed"], route_type
            )

        # Build structured response for each available route type
        available_routes = []

        for route_type in supported_route_types:
            smoothed = smoothed_routes[route_type]
            unsmoothed = unsmoothed_routes[route_type]

            # Determine which route to use (smoothed preferred, fallback to unsmoothed)
            route_geojson = None
            unsmoothed_geojson = None
            info_message = None

            if len(smoothed) > 0:
                route_geojson = smoothed[0][
                    0
                ]  # Extract the actual GeoJSON from the nested structure
                unsmoothed_geojson = unsmoothed[0][0] if len(unsmoothed) > 0 else None
            elif len(unsmoothed) > 0:
                route_geojson = unsmoothed[0][
                    0
                ]  # Extract the actual GeoJSON from the nested structure
                info_message = {
                    "warning": f"Smoothing failed for {route_type}-optimisation, returning unsmoothed route."
                }
            else:
                # No route available for this type - skip it
                continue

            # Extract optimisation metrics from route properties
            properties = (
                route_geojson["features"][0].get("properties", {})
                if route_geojson
                else {}
            )
            optimisation_metrics = self._build_optimisation_metrics(
                route_type, properties
            )

            # Build mesh and vehicle information
            mesh_info = self._build_mesh_info(instance)
            vehicle_info = self._build_vehicle_info(instance)

            # Normalize route type for consistent API response
            # Convert fuel/battery to generic "energy" type for consistency
            normalised_route_type = (
                "energy" if route_type in ("fuel", "battery") else route_type
            )

            # Build structured route object
            route_obj = {
                "type": normalised_route_type,
                "id": str(instance.id),
                "name": f"{data.get('start_name') or 'Start'} to {data.get('end_name') or 'End'} ({normalised_route_type})",
                "job": {
                    "requestedAt": data["requested"],
                    "calculatedAt": data["calculated"],
                },
                "waypoints": {
                    "start": {
                        "lat": data["start_lat"],
                        "lon": data["start_lon"],
                        "name": data.get("start_name"),
                    },
                    "end": {
                        "lat": data["end_lat"],
                        "lon": data["end_lon"],
                        "name": data.get("end_name"),
                    },
                },
                "path": route_geojson,
                "unsmoothedPath": unsmoothed_geojson,
                "optimisation": {"metrics": optimisation_metrics},
            }

            if mesh_info:
                route_obj["mesh"] = mesh_info

            if vehicle_info:
                route_obj["vehicle"] = vehicle_info

            # Add any info/warnings
            if info_message:
                route_obj["info"] = info_message
            elif data.get("info"):
                route_obj["info"] = data["info"]

            available_routes.append(route_obj)

        # Always return consistent structure - routes array with version
        result = {
            "routes": available_routes,
            "polarrouteserver-version": polarrouteserver_version,
            "tags": data.get("tags", []),
        }

        # Add error if no routes available
        if len(available_routes) == 0:
            result["error"] = "No routes available for any optimisation type."

        return result


# Shared mesh fields for serializers
MESH_FIELDS = [
    "id",
    "valid_date_start",
    "valid_date_end",
    "created",
    "lat_min",
    "lat_max",
    "lon_min",
    "lon_max",
    "name",
    "size",
    "meshiphi_version",
    "md5",
    "json",
]


class EnvironmentMeshSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvironmentMesh
        fields = MESH_FIELDS


class VehicleMeshSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleMesh
        fields = ["vehicle"] + MESH_FIELDS[1:]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "id",
            "lat",
            "lon",
            "name",
        ]
