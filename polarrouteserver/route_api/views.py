import logging
from datetime import timedelta

from celery.result import AsyncResult
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from jsonschema.exceptions import ValidationError
from meshiphi.mesh_generation.environment_mesh import EnvironmentMesh
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView
from rest_framework.reverse import reverse
from rest_framework import serializers, viewsets
from taggit.models import TaggedItem

from polar_route.config_validation.config_validator import validate_vessel_config
from polarrouteserver._version import __version__ as polarrouteserver_version
from polarrouteserver.celery import app

from .models import Job, Vehicle, Route, Mesh, Location
from .tasks import optimise_route
from .responses import (
    ResponseMixin,
    successResponseSchema,
    vehicleTypeListResponseSchema,
    routeAcceptedResponseSchema,
    recentRoutesResponseSchema,
    meshDetailResponseSchema,
    routeSchema,
    routeEvaluationResponseSchema,
    badRequestResponseSchema,
    notFoundResponseSchema,
    notAcceptableResponseSchema,
    noContentResponseSchema,
    acceptedResponseSchema,
    jobStatusResponseSchema,
)
from .serializers import (
    VehicleSerializer,
    VesselTypeSerializer,
    RouteSerializer,
    JobStatusSerializer,
    LocationSerializer,
)
from .utils import (
    evaluate_route,
    route_exists,
    select_mesh,
    select_mesh_for_route_evaluation,
)

logger = logging.getLogger(__name__)


class LoggingMixin:
    """
    Provides full logging of requests and responses
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("django.request")

    def initial(self, request, *args, **kwargs):
        try:
            self.logger.debug(
                {
                    "request": request.data,
                    "method": request.method,
                    "endpoint": request.path,
                    "user": request.user.username,
                    "ip_address": request.META.get("REMOTE_ADDR"),
                    "user_agent": request.META.get("HTTP_USER_AGENT"),
                }
            )
        except Exception:
            self.logger.exception("Error logging request data")

        super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        try:
            self.logger.debug(
                {
                    "response": response.data,
                    "status_code": response.status_code,
                    "user": request.user.username,
                    "ip_address": request.META.get("REMOTE_ADDR"),
                    "user_agent": request.META.get("HTTP_USER_AGENT"),
                }
            )
        except Exception:
            self.logger.exception("Error logging response data")

        return super().finalize_response(request, response, *args, **kwargs)


class VehicleRequestView(LoggingMixin, ResponseMixin, GenericAPIView):
    serializer_class = VehicleSerializer

    @extend_schema(
        operation_id="api_vehicle_create_request",
        request=VehicleSerializer,
        responses={
            200: successResponseSchema,
            400: badRequestResponseSchema,
            406: notAcceptableResponseSchema,
        },
    )
    def post(self, request):
        """Entry point to create vehicles"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}: {request.data}"
        )

        data = request.data

        # Using Polarroute's built in validation to validate vessel config supplied
        try:
            validate_vessel_config(data)
            logging.info("Vessel config is valid.")
        except Exception as e:
            if isinstance(e, ValidationError):
                error_message = f"Validation error: {e.message}"
            else:
                error_message = f"{e}"

            logging.error(error_message)

            return self.bad_request_response(error_message)

        # Separate out vessel_type and force_properties for checking logic below
        force_properties = data.get("force_properties", None)
        vessel_type = data["vessel_type"]

        # Check if vehicle exists already
        vehicle_queryset = Vehicle.objects.filter(vessel_type=vessel_type)

        # If the vehicle exists, obtain it and return an error if user has not specified force_properties
        if vehicle_queryset.exists():
            logger.info(f"Existing vehicle found: {vessel_type}")

            if not force_properties:
                return self.not_acceptable_response(
                    "Pre-existing vehicle was found. "
                    "To force new properties on an existing vehicle, "
                    "include 'force_properties': true in POST request."
                )

            # If a user has specified force_properties, update that vessel_type's properties
            # The vessel_type and force_properties fields need to be removed to allow updating
            vehicle_properties = data.copy()
            for key in ["vessel_type", "force_properties"]:
                vehicle_properties.pop(key, None)

            vehicle_queryset.update(**vehicle_properties)
            logger.info(f"Updating properties for existing vehicle: {vessel_type}")

            response_data = {"vessel_type": vessel_type}

        else:
            logger.info("Creating new vehicle:")

            # Create vehicle in database
            vehicle = Vehicle.objects.create(**data)

            # Prepare response data
            response_data = {"vessel_type": vehicle.vessel_type}

        return self.success_response(response_data)

    @extend_schema(
        operation_id="api_vehicle_list_retrieve",
        responses={
            200: successResponseSchema,
            204: noContentResponseSchema,
        },
    )
    def get(self, request):
        """Retrieve all vehicles"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        logger.info("Fetching all vehicles")
        vehicles = Vehicle.objects.all()

        serializer = self.serializer_class(vehicles, many=True)

        return self.success_response(serializer.data)


class VehicleDetailView(LoggingMixin, ResponseMixin, GenericAPIView):
    serializer_class = VehicleSerializer

    @extend_schema(
        operation_id="api_vehicle_retrieve_by_type",
        responses={
            200: successResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def get(self, request, vessel_type):
        """Retrieve vehicle by vessel_type"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        logger.info(f"Fetching vehicle(s) with vessel_type={vessel_type}")
        vehicles = Vehicle.objects.filter(vessel_type=vessel_type)

        serializer = self.serializer_class(vehicles, many=True)

        return self.success_response(serializer.data)

    @extend_schema(
        operation_id="api_vehicle_delete_by_type",
        responses={
            204: noContentResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def delete(self, request, vessel_type):
        """Delete vehicle by vessel_type"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        try:
            vehicle = Vehicle.objects.get(vessel_type=vessel_type)
            vehicle.delete()
            logger.info(f"Deleted vehicle with vessel_type={vessel_type}")
            return self.no_content_response(
                data={"message": f"Vehicle '{vessel_type}' deleted successfully."}
            )
        except Vehicle.DoesNotExist:
            logger.error(
                f"Vehicle with vessel_type={vessel_type} not found for deletion."
            )
            return self.not_found_response(
                f"Vehicle with vessel_type '{vessel_type}' not found."
            )


class VehicleTypeListView(LoggingMixin, ResponseMixin, GenericAPIView):
    """
    Endpoint to list all distinct vessel_types available.
    """

    serializer_class = VesselTypeSerializer

    @extend_schema(
        operation_id="api_vehicle_available_list",
        responses={
            200: vehicleTypeListResponseSchema,
        },
    )
    def get(self, request):
        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        vessel_types = Vehicle.objects.values_list("vessel_type", flat=True).distinct()
        vessel_types_list = list(vessel_types)

        if not vessel_types_list:
            logger.warning("No available vessel_types found in the database.")
            return self.success_response(
                {"vessel_types": [], "message": "No available vessel types found."}
            )

        logger.info(f"Returning {len(vessel_types_list)} distinct vessel_types")

        return self.success_response({"vessel_types": vessel_types_list})


class RouteRequestView(LoggingMixin, ResponseMixin, GenericAPIView):
    serializer_class = RouteSerializer

    @extend_schema(
        operation_id="api_route_create_request",
        request=inline_serializer(
            name="RouteCreationRequest",
            # This should be updated along with the json validation below
            fields={
                "start_lat": serializers.FloatField(
                    help_text="Starting latitude of the route."
                ),
                "start_lon": serializers.FloatField(
                    help_text="Starting longitude of the route."
                ),
                "end_lat": serializers.FloatField(
                    help_text="Ending latitude of the route."
                ),
                "end_lon": serializers.FloatField(
                    help_text="Ending longitude of the route."
                ),
                "start_name": serializers.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Name of the start point.",
                ),
                "end_name": serializers.CharField(
                    required=False, allow_null=True, help_text="Name of the end point."
                ),
                "mesh_id": serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Optional: Custom mesh ID to use for route calculation.",
                ),
                "force_new_route": serializers.BooleanField(
                    required=False,
                    default=False,
                    help_text="If true, forces recalculation even if an existing route is found.",
                ),
                "tags": serializers.ListField(
                    child=serializers.CharField(max_length=50),
                    required=False,
                    allow_null=True,
                    help_text="Optional tags for route (e.g., ['archive', 'SD056']). Can also accept a single string or comma-separated string.",
                ),
            },
        ),
        responses={
            202: routeAcceptedResponseSchema,
            400: badRequestResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def post(self, request):
        """Entry point for route requests"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}: {request.data}"
        )

        data = request.data

        # TODO validate request JSON
        try:
            start_lat = float(data["start_lat"])
            start_lon = float(data["start_lon"])
            end_lat = float(data["end_lat"])
            end_lon = float(data["end_lon"])
        except (ValueError, TypeError, KeyError) as e:
            msg = f"Invalid coordinate values provided: {e}"
            logger.error(msg)
            return self.bad_request_response(msg)

        start_name = data.get("start_name", None)
        end_name = data.get("end_name", None)
        custom_mesh_id = data.get("mesh_id", None)
        force_new_route = data.get("force_new_route", False)
        tags = data.get("tags", None)

        if custom_mesh_id:
            try:
                logger.info(f"Got custom mesh id {custom_mesh_id} in request.")
                meshes = [Mesh.objects.get(id=custom_mesh_id)]
            except Mesh.DoesNotExist:
                msg = f"Mesh id {custom_mesh_id} requested. Does not exist."
                logger.info(msg)
                return self.not_found_response(msg)
        else:
            meshes = select_mesh(start_lat, start_lon, end_lat, end_lon)

        if meshes is None:
            return self.not_found_response("No mesh available.")

        logger.debug(f"Using meshes: {[mesh.id for mesh in meshes]}")
        # TODO Future: calculate an up to date mesh if none available

        existing_route = route_exists(meshes, start_lat, start_lon, end_lat, end_lon)

        if existing_route is not None:
            if not force_new_route:
                logger.info(f"Existing route found: {existing_route}")

                # Check if there's an existing job for this route
                existing_job = existing_route.job_set.latest("datetime")

                response_data = {
                    "id": str(existing_job.id),
                    "status-url": reverse(
                        "job_detail", args=[existing_job.id], request=request
                    ),
                    "polarrouteserver-version": polarrouteserver_version,
                    "info": {
                        "message": "Pre-existing route found. Job already exists. To force new calculation, include 'force_new_route': true in POST request."
                    },
                }

                return self.accepted_response(response_data)
            else:
                logger.info(
                    f"Found existing route(s) but got force_new_route={force_new_route}, beginning recalculation."
                )

        logger.debug(
            f"Using mesh {meshes[0].id} as primary mesh with {[mesh.id for mesh in meshes[1:]]} as backup."
        )

        # Create route in database
        route = Route.objects.create(
            start_lat=start_lat,
            start_lon=start_lon,
            end_lat=end_lat,
            end_lon=end_lon,
            mesh=meshes[0],
            start_name=start_name,
            end_name=end_name,
        )

        # Add tags if provided
        if tags:
            # Handle both string and list inputs
            if isinstance(tags, str):
                # If it's a string, split by comma and strip whitespace
                tags_list = [t.strip() for t in tags.split(",") if t.strip()]
            elif isinstance(tags, list):
                tags_list = [str(t).strip() for t in tags if str(t).strip()]
            else:
                tags_list = []

            logger.info(f"Adding tags to route {route.id}: {tags_list}")
            if tags_list:
                route.tags.add(*tags_list)
                logger.info(
                    f"Route {route.id} now has tags: {[tag.name for tag in route.tags.all()]}"
                )

        # Start the task calculation
        task = optimise_route.delay(
            route.id, backup_mesh_ids=[mesh.id for mesh in meshes[1:]]
        )

        # Create database record representing the calculation job
        job = Job.objects.create(
            id=task.id,
            route=route,
        )

        # Prepare response data
        data = {
            "id": job.id,
            "status-url": reverse("job_detail", args=[job.id], request=request),
            "polarrouteserver-version": polarrouteserver_version,
        }

        return self.accepted_response(data)


class RouteDetailView(LoggingMixin, ResponseMixin, GenericAPIView):
    serializer_class = RouteSerializer

    @extend_schema(
        operation_id="api_route_retrieve_by_id",
        description="Retrieve route details by ID. Returns the route data.",
        responses={
            200: routeSchema,
            404: notFoundResponseSchema,
        },
    )
    def get(self, request, id):
        """Return route data by route ID."""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        try:
            route = Route.objects.get(id=id)
        except Route.DoesNotExist:
            return self.not_found_response(f"Route with id {id} not found.")

        data = RouteSerializer(route).data

        return self.success_response(data)


class RecentRoutesView(LoggingMixin, ResponseMixin, GenericAPIView):
    serializer_class = None  # No serializer needed - using manual response building

    def _get_celery_task_status(self, job_id, calculated_timestamp, route_info):
        """
        Get Celery task status. Uses database state to avoid Celery broker calls.
        """
        if calculated_timestamp:
            return "SUCCESS"

        if route_info and "error" in str(route_info).lower():
            return "FAILURE"

        # Handle missing job scenarios
        if not job_id:
            return "PENDING"

        # Job exists but no calculation yet - also PENDING
        return "PENDING"

    @extend_schema(
        operation_id="api_recent_routes_list",
        responses={
            200: recentRoutesResponseSchema,
        },
    )
    def get(self, request):
        """Get recent routes"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        # Only get today's routes
        routes_recent = (
            Route.objects.filter(requested__gte=timezone.now() - timedelta(hours=24))
            .select_related("job")
            .values(
                "id",
                "start_lat",
                "start_lon",
                "end_lat",
                "end_lon",
                "start_name",
                "end_name",
                "polar_route_version",
                "requested",
                "calculated",
                "info",
                "mesh_id",
                "mesh__name",
                "job__id",
            )
            .order_by("-requested")
        )

        if not routes_recent:
            return self.success_response(
                {
                    "routes": [],
                    "polarrouteserver-version": polarrouteserver_version,
                    "message": "No recent routes found for last 24 hours.",
                }
            )

        # Get route IDs for tag lookup
        route_ids = [route["id"] for route in routes_recent]

        # Get all tags for routes in one query
        route_tags = {}
        if route_ids:
            content_type = ContentType.objects.get_for_model(Route)
            tagged_items = (
                TaggedItem.objects.filter(
                    content_type=content_type, object_id__in=route_ids
                )
                .select_related("tag")
                .values("object_id", "tag__name")
            )

            for item in tagged_items:
                route_id = int(item["object_id"])
                if route_id not in route_tags:
                    route_tags[route_id] = []
                route_tags[route_id].append(item["tag__name"])

        routes_data = []
        for route in routes_recent:
            job_id = route.get("job__id")
            status = self._get_celery_task_status(
                job_id, route["calculated"], route["info"]
            )

            # Build lightweight route data
            route_data = {
                "id": route["id"],
                "start_lat": route["start_lat"],
                "start_lon": route["start_lon"],
                "end_lat": route["end_lat"],
                "end_lon": route["end_lon"],
                "start_name": route["start_name"],
                "end_name": route["end_name"],
                "polar_route_version": route["polar_route_version"],
                "requested": route["requested"].isoformat()
                if route["requested"]
                else None,
                "calculated": route["calculated"].isoformat()
                if route["calculated"]
                else None,
                "status": status,
                "route_url": reverse(
                    "route_detail", args=[route["id"]], request=request
                ),
                "tags": route_tags.get(route["id"], []),
            }

            if job_id:
                route_data["job_id"] = job_id
                route_data["job_status_url"] = reverse(
                    "job_detail", args=[job_id], request=request
                )

            # Add minimal mesh info without loading the heavy JSON
            if route["mesh_id"]:
                route_data["mesh"] = {
                    "id": route["mesh_id"],
                    "name": route["mesh__name"],
                }

            routes_data.append(route_data)

        response_data = {
            "routes": routes_data,
            "polarrouteserver-version": polarrouteserver_version,
        }

        return self.success_response(response_data)


class MeshView(LoggingMixin, ResponseMixin, APIView):
    serializer_class = None

    @extend_schema(
        operation_id="api_mesh_get",
        responses={
            200: meshDetailResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def get(self, request, id):
        "GET Meshes by id"

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        data = {"polarrouteserver-version": polarrouteserver_version}

        try:
            mesh = Mesh.objects.get(id=id)
            data.update(
                dict(
                    id=mesh.id,
                    json=mesh.json,
                    geojson=EnvironmentMesh.load_from_json(mesh.json).to_geojson(),
                )
            )

            return self.success_response(data)

        except Mesh.DoesNotExist:
            return self.not_found_response(f"Mesh with id {id} not found.")


class EvaluateRouteView(LoggingMixin, ResponseMixin, APIView):
    serializer_class = None

    @extend_schema(
        operation_id="api_route_evaluation",
        request=inline_serializer(
            name="RouteEvaluationRequest",
            fields={
                "route": serializers.JSONField(help_text="The route JSON to evaluate."),
                "custom_mesh_id": serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Optional: Custom mesh ID to use for evaluation.",
                ),
            },
        ),
        responses={
            200: routeEvaluationResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def post(self, request):
        "POST Endpoint to evaluate traveltime and fuel usage on a given route."
        data = request.data
        route_json = data.get("route", None)
        custom_mesh_id = data.get("custom_mesh_id", None)

        if custom_mesh_id:
            try:
                mesh = Mesh.objects.get(id=custom_mesh_id)
                meshes = [mesh]
            except Mesh.DoesNotExist:
                return self.not_found_response("No mesh available.")
        else:
            meshes = select_mesh_for_route_evaluation(route_json)

            if meshes is None:
                return self.not_found_response("No mesh available.")

        response_data = {"polarrouteserver-version": polarrouteserver_version}

        result_dict = evaluate_route(route_json, meshes[0])

        if result_dict is None:
            result_dict = {"error": "Route evaluation not possible."}

        response_data.update(result_dict)
        return self.success_response(response_data)


class JobView(LoggingMixin, ResponseMixin, GenericAPIView):
    """
    View for handling job status requests
    """

    serializer_class = JobStatusSerializer

    @extend_schema(
        operation_id="api_job_retrieve_status",
        responses={
            200: jobStatusResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def get(self, request, id):
        """Return status of job and route URL if complete."""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        try:
            job = Job.objects.get(id=id)
        except Job.DoesNotExist:
            return self.not_found_response(f"Job with id {id} not found.")

        serializer = JobStatusSerializer(job, context={"request": request})

        return self.success_response(serializer.data)

    @extend_schema(
        operation_id="api_job_cancel",
        responses={
            202: acceptedResponseSchema,
            404: notFoundResponseSchema,
        },
    )
    def delete(self, request, id):
        """Cancel job"""

        logger.info(
            f"{request.method} {request.path} from {request.META.get('REMOTE_ADDR')}"
        )

        try:
            job = Job.objects.get(id=id)
        except Job.DoesNotExist:
            return self.not_found_response(f"Job with id {id} not found.")

        # Store route ID for response before deletion
        route_id = job.route.id

        # Cancel the Celery task
        result = AsyncResult(id=str(id), app=app)
        result.revoke()

        # Delete the corresponding route (this will also delete the job due to CASCADE)
        job.route.delete()

        return self.accepted_response(
            {
                "message": f"Job {id} cancellation requested and route {route_id} deleted.",
                "job_id": str(job.id),
                "route_id": route_id,
            }
        )


@extend_schema_view(
    list=extend_schema(
        responses={200: LocationSerializer(many=True)},
        description="List all available locations",
    ),
    retrieve=extend_schema(
        responses={
            200: LocationSerializer,
            404: notFoundResponseSchema,
        },
        description="Retrieve a specific location by ID",
    ),
)
class LocationViewSet(LoggingMixin, ResponseMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Location.objects.all().order_by("name")
    serializer_class = LocationSerializer

    # At present this is just a GET endpoint.
    # In future this endpoint and the Location model could support a lot of functionality,
    # e.g. user ownership of locations, search of locations by name,
    # return only locations which are covered by current meshes etc.
