import rest_framework.status
from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response


class ResponseMixin:
    """
    Mixin providing standardized API response methods.

    Ensures consistent response formatting across all API endpoints and
    provides response methods that correspond to the standardized schema objects
    defined in this module.

    Usage:
        class MyView(ResponseMixin, APIView):
            def get(self, request):
                return self.success_response({"data": "example"})

    Schema Integration:
        Each method in this mixin corresponds to a schema object:
        - success_response() -> successResponseSchema (200)
        - accepted_response() -> acceptedResponseSchema (202)
        - no_content_response() -> noContentResponseSchema (204)
        - bad_request_response() -> badRequestResponseSchema (400)
        - not_found_response() -> notFoundResponseSchema (404)
        - not_acceptable_response() -> notAcceptableResponseSchema (406)
    """

    def success_response(self, data, status_code=rest_framework.status.HTTP_200_OK):
        """
        Return standardized success response.
        Corresponds to: successResponseSchema (200)
        """
        return Response(
            data,
            headers={"Content-Type": "application/json"},
            status=status_code,
        )

    def accepted_response(self, data):
        """
        Return standardized accepted response.
        Corresponds to: acceptedResponseSchema (202)
        """
        return Response(
            data,
            headers={"Content-Type": "application/json"},
            status=rest_framework.status.HTTP_202_ACCEPTED,
        )

    def no_content_response(self, data=None, message=None):
        """
        Return standardized no content response.
        Corresponds to: noContentResponseSchema (204)
        """
        response_data = data or {}
        if message:
            response_data["message"] = message
        return Response(
            data=response_data,
            headers={"Content-Type": "application/json"},
            status=rest_framework.status.HTTP_204_NO_CONTENT,
        )

    def bad_request_response(
        self, error_message, status_code=rest_framework.status.HTTP_400_BAD_REQUEST
    ):
        """
        Return standardized bad request response.
        Corresponds to: badRequestResponseSchema (400)
        """
        return Response(
            {"error": error_message},
            headers={"Content-Type": "application/json"},
            status=status_code,
        )

    def not_found_response(self, message):
        """
        Return standardized not found response.
        Corresponds to: notFoundResponseSchema (404)
        """
        return Response(
            {"error": message},
            headers={"Content-Type": "application/json"},
            status=rest_framework.status.HTTP_404_NOT_FOUND,
        )

    def not_acceptable_response(self, message):
        """
        Return standardized not acceptable response.
        Corresponds to: notAcceptableResponseSchema (406)
        """
        return Response(
            {"error": message},
            headers={"Content-Type": "application/json"},
            status=rest_framework.status.HTTP_406_NOT_ACCEPTABLE,
        )


# HTTP 200 Response Schemas
successResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="SuccessResponse",
        fields={
            "data": serializers.JSONField(help_text="Response data"),
        },
    ),
    description="Operation completed successfully.",
)

vehicleTypeListResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="VehicleTypeListResponse",
        fields={
            "vessel_types": serializers.ListField(
                child=serializers.CharField(),
                help_text="List of available vessel types.",
            ),
        },
    ),
    description="List of available vessel types retrieved successfully.",
)

recentRoutesResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="RecentRoutesResponse",
        fields={
            "routes": serializers.ListField(
                child=serializers.DictField(),
                help_text="List of recent routes with status information",
            ),
        },
    ),
    description="List of recent routes retrieved successfully.",
)

meshDetailResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="MeshDetailResponse",
        fields={
            "polarrouteserver-version": serializers.CharField(
                help_text="Server version"
            ),
            "id": serializers.UUIDField(help_text="Mesh ID"),
            "json": serializers.JSONField(help_text="Mesh JSON data"),
            "geojson": serializers.JSONField(help_text="Mesh GeoJSON data"),
        },
    ),
    description="Mesh details retrieved successfully.",
)

routeEvaluationResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="RouteEvaluationResponse",
        fields={
            "polarrouteserver-version": serializers.CharField(
                help_text="Server version"
            ),
            "evaluation_results": serializers.DictField(
                help_text="Route evaluation results"
            ),
        },
    ),
    description="Route evaluated successfully.",
)

routeSchema = OpenApiResponse(
    response=inline_serializer(
        name="Route",
        fields={
            "type": serializers.CharField(
                help_text="Route optimization type (traveltime/fuel)"
            ),
            "id": serializers.CharField(help_text="Route ID"),
            "name": serializers.CharField(help_text="Descriptive route name"),
            "job": serializers.DictField(
                help_text="Job information with requested/calculated timestamps"
            ),
            "waypoints": serializers.DictField(
                help_text="Start and end waypoint information"
            ),
            "path": serializers.JSONField(help_text="GeoJSON route data"),
            "unsmoothedPath": serializers.JSONField(
                allow_null=True, help_text="Unsmoothed GeoJSON route data"
            ),
            "optimisation": serializers.DictField(help_text="Optimization metrics"),
            "mesh": serializers.DictField(
                allow_null=True, help_text="Mesh information"
            ),
            "info": serializers.DictField(
                allow_null=True, help_text="Additional route information or warnings"
            ),
            "polarrouteserver-version": serializers.CharField(
                help_text="Server version"
            ),
        },
    ),
    description="Route details retrieved successfully.",
)

# HTTP 202 Response Schemas
acceptedResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="AcceptedResponse",
        fields={
            "data": serializers.JSONField(
                help_text="Response data for accepted request"
            ),
        },
    ),
    description="Request accepted for processing.",
)

routeAcceptedResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="RouteAcceptedResponse",
        fields={
            "id": serializers.UUIDField(help_text="Job ID for route calculation"),
            "status-url": serializers.URLField(help_text="URL to check job status"),
            "polarrouteserver-version": serializers.CharField(
                help_text="Server version"
            ),
            "info": serializers.DictField(
                required=False, help_text="Additional information"
            ),
        },
    ),
    description="Route calculation job accepted.",
)

# HTTP 204 Response Schemas
noContentResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="NoContentResponse",
        fields={
            "message": serializers.CharField(
                required=False,
                help_text="Optional message describing the empty result.",
            ),
        },
    ),
    description="No content available.",
)

# HTTP 400 Response Schemas
badRequestResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="BadRequestResponse",
        fields={
            "error": serializers.CharField(
                help_text="Error message describing what went wrong."
            ),
        },
    ),
    description="Bad request - invalid input data or malformed request.",
)

# HTTP 404 Response Schemas
notFoundResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="NotFoundResponse",
        fields={
            "error": serializers.CharField(
                help_text="Error message indicating resource not found."
            ),
        },
    ),
    description="Requested resource not found.",
)


# HTTP 406 Response Schemas
notAcceptableResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="NotAcceptableResponse",
        fields={
            "error": serializers.CharField(
                help_text="Error message describing the conflict or why the request is not acceptable."
            ),
        },
    ),
    description="Not acceptable - request conflicts with current resource state.",
)

jobStatusResponseSchema = OpenApiResponse(
    response=inline_serializer(
        name="JobStatusResponse",
        fields={
            "id": serializers.UUIDField(help_text="ID of the job."),
            "status": serializers.ChoiceField(
                choices=[
                    ("PENDING", "Task is waiting for execution or unknown task id"),
                    ("STARTED", "Task has been started"),
                    ("SUCCESS", "Task executed successfully"),
                    ("FAILURE", "Task failed with an exception"),
                    ("RETRY", "Task is being retried after failure"),
                    ("REVOKED", "Task was revoked/cancelled"),
                ],
                help_text="Current status of the job. These are standard Celery task states.",
            ),
            "polarrouteserver-version": serializers.CharField(
                help_text="Version of PolarRoute-server."
            ),
            "route_id": serializers.UUIDField(help_text="ID of the associated route."),
            "created": serializers.DateTimeField(help_text="When the job was created."),
            "info": serializers.DictField(
                required=False,
                help_text="Additional information or error details if status is FAILURE.",
            ),
            "route_url": serializers.URLField(
                required=False,
                help_text="URL to retrieve the route data when status is SUCCESS.",
            ),
        },
    ),
    description="Job status retrieved successfully.",
)
