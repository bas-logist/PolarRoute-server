import json
import uuid
from datetime import timedelta
from unittest.mock import patch, PropertyMock

import celery.states
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory
import pytest

from polarrouteserver.route_api.views import (
    EvaluateRouteView,
    MeshView,
    VehicleRequestView,
    VehicleDetailView,
    VehicleTypeListView,
    RouteRequestView,
    RouteDetailView,
    RecentRoutesView,
    LocationViewSet,
    JobView,
)
from polarrouteserver.route_api.models import Job, Route
from polarrouteserver.route_api.tasks import optimise_route
from .utils import add_test_mesh_to_db


class TestVehicleRequest(TestCase):
    """
    Test case for the Vehicle API endpoints. Covers:
    - Creating and updating vehicles
    - Validating input data for vehicles
    - Retrieving vehicle records
    - Deleting vehicle records
    """

    with open(settings.TEST_VEHICLE_PATH) as fp:
        vessel_config = json.load(fp)

    data = dict(vessel_config)

    def setUp(self):
        """
        Set up test environment for each test case, API request factory and test data.
        """
        self.factory = APIRequestFactory()
        self.data = self.__class__.data.copy()

    def post_vehicle(self, data):
        """
        Helper method to send a POST request to create or update a vehicle.

        Args:
            data (dict): The vehicle data payload.

        Returns:
            Response: Response object returned.
        """
        request = self.factory.post(
            "/api/vehicle", data=data, format="json"
        )
        return VehicleRequestView.as_view()(request)

    def test_create_update_vehicle(self):
        """
        Test creating a new vehicle, handling duplicates, and using force_properties.
        """
        data = self.data.copy()
        response = self.post_vehicle(data)
        self.assertEqual(response.status_code, 200)

        duplicate_response = self.post_vehicle(data)
        self.assertEqual(duplicate_response.status_code, 406)
        self.assertIn("error", duplicate_response.data)
        self.assertIn(
            "Pre-existing vehicle was found.", duplicate_response.data["error"]
        )

        data.update({"force_properties": True})
        response_force = self.post_vehicle(data)
        self.assertEqual(response_force.status_code, 200)
        self.assertEqual(
            response.data.get("vessel_type"),
            response_force.data.get("vessel_type"),
        )

    def test_missing_property(self):
        """
        Test that omitting a required property (e.g., 'max_speed') results in validation error.
        """
        missing_property = self.data.copy()
        missing_property.pop("max_speed", None)
        response = self.post_vehicle(missing_property)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn(
            "Validation error: 'max_speed' is a required property",
            response.data["error"],
        )

    def test_wrong_type(self, data=data):
        """
        Test that submitting a wrong data type (e.g., string for 'max_speed') fails.
        """
        wrong_type = self.data.copy()
        wrong_type["max_speed"] = "really fast"
        response = self.post_vehicle(wrong_type)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn(
            "Validation error: 'really fast' is not of type 'number'",
            response.data["error"],
        )

    def test_type_error_on_invalid_input(self):
        """
        Test that submitting a non-dictionary returns a validation error.
        """
        invalid_data = ["this", "is", "not", "a", "dict"]
        response = self.post_vehicle(invalid_data)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn("Expected 'str' or 'dict'", response.data["error"])

    def test_get_vehicle(self):
        """
        Test GET requests to fetch specific or all vehicles.
        """
        self.post_vehicle(self.data)

        # Test GET all vehicles
        request_all = self.factory.get("/api/vehicle")
        response_all = VehicleRequestView.as_view()(request_all)

        self.assertEqual(response_all.status_code, 200)
        self.assertTrue(len(response_all.data) >= 1)
        self.assertIn("vessel_type", response_all.data[0])

        # Test GET specific vehicle
        vessel_type = self.data["vessel_type"]
        request_specific = self.factory.get(f"/api/vehicle/{vessel_type}/")
        response_specific = VehicleDetailView.as_view()(
            request_specific, vessel_type=vessel_type
        )

        self.assertEqual(response_specific.status_code, 200)
        self.assertTrue(len(response_specific.data) >= 1)
        self.assertTrue(
            all(v["vessel_type"] == vessel_type for v in response_specific.data)
        )

    def test_delete_vehicle_success(self):
        """
        Test successful deletion of a vehicle.
        """
        self.post_vehicle(self.data)
        vessel_type = self.data["vessel_type"]

        request_delete = self.factory.delete(f"/api/vehicle/{vessel_type}/")
        response_delete = VehicleDetailView.as_view()(
            request_delete, vessel_type=vessel_type
        )

        self.assertEqual(response_delete.status_code, 204)
        self.assertIn("message", response_delete.data)

    def test_delete_vehicle_without_vessel_type(self):
        """
        Test deletion attempt without specifying a 'vessel_type' fails.
        We have intentionally not implemented this method.
        """
        request_delete = self.factory.delete("/api/vehicle/")
        response_delete = VehicleRequestView.as_view()(
            request_delete
        )

        self.assertEqual(response_delete.status_code, 405)

    def test_delete_vehicle_not_found(self):
        """
        Test deletion of a non-existent vehicle.
        """
        vessel_type = "non_existent_type"
        request_delete = self.factory.delete(f"/api/vehicle/{vessel_type}/")
        response_delete = VehicleDetailView.as_view()(
            request_delete, vessel_type=vessel_type
        )

        self.assertEqual(response_delete.status_code, 404)
        self.assertIn("error", response_delete.data)
        self.assertIn(vessel_type, response_delete.data["error"])


class TestVehicleTypeListView(TestCase):
    """
    Test case for the VehicleTypeListView endpoint at /api/vehicle/available, listing all available
    vehicles.
    """

    with open(settings.TEST_VEHICLE_PATH) as fp:
        vessel_config = json.load(fp)

    data = dict(vessel_config)

    def setUp(self):
        """
        Set up test environment for each test case, API request factory and test data.
        """
        self.factory = APIRequestFactory()
        self.data = self.__class__.data.copy()

    def post_vehicle(self, data):
        """
        Helper method to send a POST request to create or update a vehicle.

        Args:
            data (dict): The vehicle data.

        Returns:
            Response: Response object returned.
        """
        request = self.factory.post(
            "/api/vehicle", data=data, format="json"
        )
        return VehicleRequestView.as_view()(request)

    def test_get_vessel_types_empty(self):
        """
        Test the endpoint returns 200 OK with empty array when no vehicles exist.
        """
        request = self.factory.get("/api/vehicle/available")
        response = VehicleTypeListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("vessel_types", response.data)
        self.assertEqual(response.data["vessel_types"], [])
        self.assertIn("message", response.data)
        self.assertEqual(response.data["message"], "No available vessel types found.")

    def test_get_vessel_types_single_vehicle(self):
        """
        Test the endpoint after creating a single vehicle.
        """
        self.post_vehicle(self.data)

        request = self.factory.get("/api/vehicle/available")
        response = VehicleTypeListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("vessel_types", response.data)
        self.assertEqual(len(response.data["vessel_types"]), 1)
        self.assertIn(self.data["vessel_type"], response.data["vessel_types"])

    def test_get_vessel_types_multiple_vehicles(self):
        """
        Test the endpoint after creating vehicles with multiple distinct vessel_types.
        """
        data1 = self.data.copy()
        data2 = self.data.copy()
        data2["vessel_type"] = "Boaty McBoatface"

        self.post_vehicle(data1)
        self.post_vehicle(data2)

        request = self.factory.get("/api/vehicle/available")
        response = VehicleTypeListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("vessel_types", response.data)
        self.assertEqual(len(response.data["vessel_types"]), 2)
        self.assertCountEqual(
            response.data["vessel_types"],
            [data1["vessel_type"], data2["vessel_type"]],
        )


class TestRouteRequest(TestCase):
    def setUp(self):
        add_test_mesh_to_db()
        self.factory = APIRequestFactory()

    def test_custom_mesh_id(self):
        """Test that non-existent mesh id results in correct error message."""

        data = {
            "start_lat": 0.0,
            "start_lon": 0.0,
            "end_lat": 1.0,
            "end_lon": 1.0,
            "mesh_id": 999,
        }

        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        response = RouteRequestView.as_view()(request)

        self.assertEqual(response.status_code, 404)
        self.assertIn("Does not exist.", response.data["error"])

    def test_request_route(self):
        data = {
            "start_lat": 0.0,
            "start_lon": 0.0,
            "end_lat": 1.0,
            "end_lon": 1.0,
        }

        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        response = RouteRequestView.as_view()(request)

        self.assertEqual(response.status_code, 202)

        assert f"api/job/{response.data.get('id')}" in response.data.get("status-url")
        assert isinstance(uuid.UUID(response.data.get("id")), uuid.UUID)

        # Test that requesting the same route doesn't start a new job.
        # request the same route parameters
        request = self.factory.post(
            "/api/route", data=data, format="json"
        )
        response2 = RouteRequestView.as_view()(request) # Changed View
        assert response.data.get("id") == response2.data.get("id")
        assert response.data.get("polarrouteserver-version") == response2.data.get(
            "polarrouteserver-version"
        )
        assert f"api/job/{response.data.get('id')}" in response2.data.get(
            "status-url"
        )

    def test_request_route_with_tags(self):
        """Test that routes can be created with optional tags."""
        data = {
            "start_lat": 0.1,
            "start_lon": 0.1,
            "end_lat": 0.9,
            "end_lon": 0.9,
            "start_name": "Test Start",
            "end_name": "Test End",
            "tags": ["archive_test"],
        }

        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        response = RouteRequestView.as_view()(request)

        self.assertEqual(response.status_code, 202)

        # Verify the route was created with the correct tag
        from polarrouteserver.route_api.models import Route
        route = Route.objects.filter(
            start_lat=0.1,
            start_lon=0.1,
            end_lat=0.9,
            end_lon=0.9
        ).first()

        self.assertIsNotNone(route)
        self.assertIn("archive_test", [tag.name for tag in route.tags.all()])

    def test_request_route_without_tags(self):
        """Test that routes can be created without tags (tag is optional)."""
        data = {
            "start_lat": 0.2,
            "start_lon": 0.2,
            "end_lat": 0.8,
            "end_lon": 0.8,
        }

        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        response = RouteRequestView.as_view()(request)

        self.assertEqual(response.status_code, 202)

        # Verify the route was created without any tags
        from polarrouteserver.route_api.models import Route
        route = Route.objects.filter(
            start_lat=0.2,
            start_lon=0.2,
            end_lat=0.8,
            end_lon=0.8
        ).first()

        self.assertIsNotNone(route)
        self.assertEqual(route.tags.count(), 0)

    def test_request_route_with_comma_separated_tags(self):
        """Test that routes can be created with comma-separated tag string."""
        data = {
            "start_lat": 0.3,
            "start_lon": 0.3,
            "end_lat": 0.7,
            "end_lon": 0.7,
            "tags": "archive,experiment, test_tag ",  # Test comma separation and whitespace
        }

        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        response = RouteRequestView.as_view()(request)
        self.assertEqual(response.status_code, 202)

        # Verify the route was created with the correct tags
        from polarrouteserver.route_api.models import Route
        route = Route.objects.filter(
            start_lat=0.3,
            start_lon=0.3,
            end_lat=0.7,
            end_lon=0.7
        ).first()

        self.assertIsNotNone(route)
        tag_names = [tag.name for tag in route.tags.all()]
        self.assertIn("archive", tag_names)
        self.assertIn("experiment", tag_names)
        self.assertIn("test_tag", tag_names)
        self.assertEqual(len(tag_names), 3)


    def test_request_route_with_invalid_tags_type(self):
        """Test that routes handle invalid tag types gracefully."""
        data = {
            "start_lat": 0.5,
            "start_lon": 0.5,
            "end_lat": 0.5,
            "end_lon": 0.5,
            "tags": {"invalid": "dict"},  # Invalid type should result in no tags
        }

        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        response = RouteRequestView.as_view()(request)
        self.assertEqual(response.status_code, 202)

        # Verify the route was created without tags
        from polarrouteserver.route_api.models import Route
        route = Route.objects.filter(
            start_lat=0.5,
            start_lon=0.5,
            end_lat=0.5,
            end_lon=0.5
        ).first()

        self.assertIsNotNone(route)
        self.assertEqual(route.tags.count(), 0)

    def test_evaluate_route(self):
        with open(settings.TEST_ROUTE_PATH) as fp:
            route_json = json.load(fp)

        data = dict(route=route_json)

        request = self.factory.post(
            "/api/evaluate_route", data=data, format="json"
        )

        response = EvaluateRouteView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_evaluate_out_of_mesh_waypoints(self):
        with open(settings.TEST_ROUTE_OOM_PATH) as fp:
            route_json = json.load(fp)

        data = dict(route=route_json)

        request = self.factory.post(
            "/api/evaluate_route", data=data, format="json"
        )

        response = EvaluateRouteView.as_view()(request)
        self.assertEqual(response.status_code, 404)


pytestmark = pytest.mark.django_db


@pytest.mark.usefixtures("celery_app", "celery_worker", "celery_enable_logging")
@pytest.mark.django_db
class TestRouteStatus:

    pytestmark = pytest.mark.django_db

    def setUp(self):
        self.factory = APIRequestFactory()
        mesh = add_test_mesh_to_db()
        self.route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=2.0, end_lon=2.0, mesh=mesh
        )
        optimise_route(self.route.id)

    def test_get_status_pending(self):
        
        self.setUp()
        
        self.job = Job.objects.create(
            id=uuid.uuid1(),
            route=self.route,
        )

        request = self.factory.get(f"/api/job/{self.job.id}")

        response = JobView.as_view()(request, id=self.job.id)

        assert response.status_code == 200

        assert response.data.get("status") == "PENDING"

    def test_get_status_complete(self):

        self.setUp()

        with patch(
            "polarrouteserver.route_api.views.AsyncResult.state",
            new_callable=PropertyMock,
        ) as mock_job_status:
            mock_job_status.return_value = celery.states.SUCCESS

            self.job = Job.objects.create(
                id=uuid.uuid1(),
                route=self.route,
            )

            request = self.factory.get(f"/api/job/{self.job.id}")

            response = JobView.as_view()(request, id=self.job.id)

            assert response.status_code == 200
            assert response.data.get("status") == "SUCCESS"
            assert "route_url" in response.data

    def test_request_out_of_mesh(self):

        self.setUp()

        with open(settings.TEST_MESH_PATH) as f:
            mesh = json.load(f)

        # Request a point that is out of mesh
        lat_min = mesh["config"]["mesh_info"]["region"]["lat_min"]
        lat_max = mesh["config"]["mesh_info"]["region"]["lat_max"]
        lon_min = mesh["config"]["mesh_info"]["region"]["long_min"]
        lon_max = mesh["config"]["mesh_info"]["region"]["long_max"]

        data = {
            "start_lat": lat_min - 5,
            "start_lon": lon_min - 5,
            "end_lat": abs(lat_max - lat_min) / 2,
            "end_lon": abs(lon_max - lon_min) / 2,
        }

        # make route request
        request = self.factory.post(
            "/api/route", data=data, format="json"
        )

        # using try except to ignore deliberate error in celery task in test envrionment
        # in production, celery handles this
        try:
            post_response = RouteRequestView.as_view()(request)
        except AssertionError:
            pass

        assert post_response.status_code == 404
        assert post_response.data["error"] == "No mesh available."


@pytest.mark.usefixtures("celery_app", "celery_worker", "celery_enable_logging")
@pytest.mark.django_db
class TestCancelRoute:

    pytestmark = pytest.mark.django_db

    def setUp(self):
        self.factory = APIRequestFactory()
        mesh = add_test_mesh_to_db()
        self.route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=2.0, end_lon=2.0, mesh=mesh
        )

    def test_cancel_route(self):

        self.setUp()
        self.job = Job.objects.create(
            id=uuid.uuid1(),
            route=self.route,
        )

        # Store route ID for checking deletion later
        route_id = self.route.id
        
        request = self.factory.delete(f"/api/job/{self.job.id}")

        response = JobView.as_view()(request, id=self.job.id)

        assert response.status_code == 202
        
        # Test the response includes job and route info
        assert "message" in response.data
        assert "job_id" in response.data
        assert "route_id" in response.data
        assert str(self.job.id) in response.data["message"]
        assert response.data["job_id"] == str(self.job.id)
        assert response.data["route_id"] == route_id
        assert "deleted" in response.data["message"]
        
        # Verify that the route has been deleted
        with pytest.raises(Route.DoesNotExist):
            Route.objects.get(id=route_id)

    def test_cancel_nonexistent_job(self):
        """
        Test that attempting to cancel a non-existent job returns 404.
        """
        self.setUp()
        
        fake_job_id = uuid.uuid4()
        request = self.factory.delete(f"/api/job/{fake_job_id}")

        response = JobView.as_view()(request, id=fake_job_id)

        assert response.status_code == 404
        assert "error" in response.data
        assert str(fake_job_id) in response.data["error"]


class TestRouteDetailView(TestCase):
    """
    Test case for the RouteDetailView endpoint that returns route data by route ID.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.mesh = add_test_mesh_to_db()
        
        # Create a test route with minimal data
        self.route = Route.objects.create(
            start_lat=60.0,
            start_lon=-1.0,
            end_lat=61.0,
            end_lon=-2.0,
            mesh=self.mesh,
            start_name="Test Start",
            end_name="Test End",
            json=None,
            json_unsmoothed=None,
            polar_route_version="0.2.0",
            info={"message": "Test route"}
        )

    def test_get_route_success(self):
        """
        Test successful retrieval of route data by ID.
        """
        request = self.factory.get(f"/api/route/{self.route.id}")
        response = RouteDetailView.as_view()(request, id=self.route.id)

        self.assertEqual(response.status_code, 200)
        
        # Since route has no json data, it should return error
        self.assertIn("routes", response.data)
        self.assertEqual(len(response.data["routes"]), 0)
        self.assertIn("error", response.data)
        self.assertIn("polarrouteserver-version", response.data)

    def test_get_route_not_found(self):
        """
        Test that requesting a non-existent route ID returns 404.
        """
        non_existent_id = 99999
        request = self.factory.get(f"/api/route/{non_existent_id}")
        response = RouteDetailView.as_view()(request, id=non_existent_id)

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)
        self.assertIn(str(non_existent_id), response.data["error"])

    def test_get_route_with_minimal_data(self):
        """
        Test retrieval of route with minimal required data (no optional fields).
        """
        minimal_route = Route.objects.create(
            start_lat=50.0,
            start_lon=0.0,
            end_lat=51.0,
            end_lon=1.0,
            mesh=self.mesh
            # No optional fields like start_name, end_name, json, etc.
        )

        request = self.factory.get(f"/api/route/{minimal_route.id}")
        response = RouteDetailView.as_view()(request, id=minimal_route.id)

        self.assertEqual(response.status_code, 200)
        
        # Should return consistent structure with empty routes and error
        self.assertIn("routes", response.data)
        self.assertEqual(len(response.data["routes"]), 0)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "No routes available for any optimisation type.")
        self.assertIn("polarrouteserver-version", response.data)


class TestGetRecentRoutesAndMesh(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.mesh = add_test_mesh_to_db()
        # Create routes with calculated timestamps so they'll be found by the recent routes filter
        now = timezone.now()
        within_24_hours = now - timedelta(hours=18)
        longer_than_24_hours = now - timedelta(hours=25)
        self.route1 = Route.objects.create(
            start_lat=0.0, start_lon=0.0, end_lat=0.0, end_lon=0.0, 
            mesh=self.mesh, calculated=now, requested=now,
        )
        self.route2 = Route.objects.create(
            start_lat=1.0, start_lon=1.0, end_lat=1.0, end_lon=0.0, 
            mesh=self.mesh, calculated=within_24_hours, requested=within_24_hours,
        )
        self.route3 = Route.objects.create(
            start_lat=1.0, start_lon=1.0, end_lat=1.0, end_lon=0.0, 
            mesh=self.mesh, calculated=longer_than_24_hours, requested=longer_than_24_hours,
        )
        
        self.job1 = Job.objects.create(id=uuid.uuid1(), route=self.route1)
        self.job2 = Job.objects.create(id=uuid.uuid1(), route=self.route2)
        self.job3 = Job.objects.create(id=uuid.uuid1(), route=self.route3)

    def test_recent_routes_request(self):

        request = self.factory.get(f"/api/recent_routes")

        response = RecentRoutesView.as_view()(request)

        assert response.status_code == 200
        assert "routes" in response.data
        assert "polarrouteserver-version" in response.data
        assert len(response.data["routes"]) == 2

    def test_recent_routes_response_structure(self):
        """Test that RecentRoutesView response has correct structure and field types"""
        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)

        # Top level response structure
        assert response.status_code == 200
        assert isinstance(response.data, dict)
        assert "routes" in response.data
        assert "polarrouteserver-version" in response.data
        assert isinstance(response.data["polarrouteserver-version"], str)
        
        # Routes array validation  
        routes = response.data["routes"]
        assert isinstance(routes, list)
        assert len(routes) == 2

        # Individual route structure validation
        for route in routes:
            assert isinstance(route, dict)
            
            required_fields = [
                "id", "start_lat", "start_lon", "end_lat", "end_lon", 
                "requested", "status", "route_url"
            ]
            for field in required_fields:
                assert field in route, f"Missing required field: {field}"
            
            assert isinstance(route["id"], int)
            assert isinstance(route["start_lat"], float)
            assert isinstance(route["start_lon"], float) 
            assert isinstance(route["end_lat"], float)
            assert isinstance(route["end_lon"], float)
            assert isinstance(route["requested"], str)
            assert isinstance(route["status"], str)
            assert isinstance(route["route_url"], str)
            
            # Optional fields that may be present
            if "start_name" in route:
                assert route["start_name"] is None or isinstance(route["start_name"], str)
            if "end_name" in route:
                assert route["end_name"] is None or isinstance(route["end_name"], str)
            if "calculated" in route:
                assert route["calculated"] is None or isinstance(route["calculated"], str)
            if "polar_route_version" in route:
                assert route["polar_route_version"] is None or isinstance(route["polar_route_version"], str)
            if "job_id" in route:
                assert isinstance(route["job_id"], (str, type(uuid.uuid4())))
            if "job_status_url" in route:
                assert isinstance(route["job_status_url"], str)
            if "mesh" in route:
                assert isinstance(route["mesh"], dict)
                assert "id" in route["mesh"]
                assert "name" in route["mesh"]

    def test_recent_routes_status_calculation(self):
        """Test that status is calculated correctly based on route state"""
        # Create route without calculated timestamp (PENDING)
        pending_route = Route.objects.create(
            start_lat=2.0, start_lon=2.0, end_lat=2.0, end_lon=2.0,
            mesh=self.mesh
        )
        # Job is required for route to appear in recent routes query
        Job.objects.create(id=uuid.uuid4(), route=pending_route)
        
        # Create route with error info (FAILURE)
        error_route = Route.objects.create(
            start_lat=3.0, start_lon=3.0, end_lat=3.0, end_lon=3.0,
            mesh=self.mesh,
            info="Route calculation error occurred"
        )
        # Job is required for route to appear in recent routes query  
        Job.objects.create(id=uuid.uuid4(), route=error_route)

        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)

        routes_by_lat = {route["start_lat"]: route for route in response.data["routes"]}
        
        # Calculated routes should be SUCCESS
        assert routes_by_lat[0.0]["status"] == "SUCCESS"
        assert routes_by_lat[1.0]["status"] == "SUCCESS"
        
        # Pending route should be PENDING
        assert routes_by_lat[2.0]["status"] == "PENDING"
        
        # Error route should be FAILURE  
        assert routes_by_lat[3.0]["status"] == "FAILURE"

    def test_recent_routes_no_content_response(self):
        """Test response when no routes exist for today returns 200 OK with empty array"""
        # Clear all routes created in setUp
        Route.objects.all().delete()
        
        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)
        
        assert response.status_code == 200
        assert "routes" in response.data
        assert response.data["routes"] == []
        assert "polarrouteserver-version" in response.data
        assert isinstance(response.data["polarrouteserver-version"], str)
        assert "message" in response.data
        assert "No recent routes found" in response.data["message"]

    def test_recent_routes_includes_job_info_when_present(self):
        """Test that job_id and job_status_url are included when job exists"""
        request = self.factory.get("/api/recent_routes") 
        response = RecentRoutesView.as_view()(request)
        
        routes = response.data["routes"]
        for route in routes:
            # All test routes have jobs, so these fields should be present
            assert "job_id" in route
            assert "job_status_url" in route
            assert isinstance(route["job_id"], (str, type(uuid.uuid4())))
            assert "/api/job/" in route["job_status_url"]

    def test_recent_routes_includes_mesh_info(self):
        """Test that mesh information is included correctly"""
        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)
        
        routes = response.data["routes"]
        for route in routes:
            assert "mesh" in route
            mesh_info = route["mesh"]
            assert isinstance(mesh_info, dict)
            assert "id" in mesh_info
            assert "name" in mesh_info
            assert isinstance(mesh_info["id"], int)
            # mesh name could be None or string
            assert mesh_info["name"] is None or isinstance(mesh_info["name"], str)

    def test_recent_routes_datetime_formatting(self):
        """Test that datetime fields are properly formatted as ISO strings"""
        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)
        
        routes = response.data["routes"]
        for route in routes:
            # Requested should always be present and ISO formatted
            assert "requested" in route
            requested = route["requested"]
            assert isinstance(requested, str)
            # Basic ISO format check (should contain T and end with timezone)
            assert "T" in requested
            
            # Calculated should be present since setUp routes have calculated timestamps
            if "calculated" in route and route["calculated"]:
                calculated = route["calculated"]
                assert isinstance(calculated, str)
                assert "T" in calculated

    def test_recent_routes_url_generation(self):
        """Test that URLs are properly generated with request context"""
        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)
        
        routes = response.data["routes"]
        for route in routes:
            # Route URL should be present and contain route ID
            route_url = route["route_url"]
            assert isinstance(route_url, str)
            assert f"/api/route/{route['id']}" in route_url
            
            # Job status URL should contain job ID
            if "job_status_url" in route:
                job_status_url = route["job_status_url"] 
                assert isinstance(job_status_url, str)
                assert f"/api/job/{route['job_id']}" in job_status_url

    def test_recent_routes_includes_tags(self):
        """Test that recent routes include tag information."""
        # Create a route with tags
        from polarrouteserver.route_api.models import Route
        route = Route.objects.create(
            start_lat=1.0,
            start_lon=1.0,
            end_lat=2.0,
            end_lon=2.0,
        )
        route.tags.add("test_tag", "recent_test")
        
        request = self.factory.get("/api/recent_routes")
        response = RecentRoutesView.as_view()(request)
        
        self.assertEqual(response.status_code, 200)
        routes = response.data["routes"]
        
        # Find our test route in the response
        test_route = None
        for route_data in routes:
            if route_data["id"] == route.id:
                test_route = route_data
                break
        
        self.assertIsNotNone(test_route)
        self.assertIn("tags", test_route)
        self.assertIsInstance(test_route["tags"], list)
        self.assertIn("test_tag", test_route["tags"])
        self.assertIn("recent_test", test_route["tags"])

    def test_mesh_get(self):

        request = self.factory.get(f"/api/mesh/{self.mesh.id}")

        response = MeshView.as_view()(request, self.mesh.id)

        assert response.status_code == 200
        assert response.data.get("json") is not None
        assert response.data.get("geojson") is not None

    def test_mesh_not_found(self):
        """Test that requesting a non-existent mesh returns 404."""
        non_existent_id = 9999
        request = self.factory.get(f"/api/mesh/{non_existent_id}")

        response = MeshView.as_view()(request, id=non_existent_id)

        assert response.status_code == 404
        assert "error" in response.data
        assert f"Mesh with id {non_existent_id} not found" in response.data["error"]

class TestGetLocations(TestCase):
    fixtures = ["locations_bas.json"]

    def setUp(self):
        self.factory = APIRequestFactory()
        self.location_id = 1
        self.location_expected_name = "Bird Island"

    def test_location_list_request(self):
        request = self.factory.get(f"/api/location")

        response = LocationViewSet.as_view({'get': 'list'})(request)

        assert response.status_code == 200
        assert len(response.data) > 1
    
    def test_location_single_request(self):
        request = self.factory.get(f"/api/location/{self.location_id}")

        response = LocationViewSet.as_view({'get': 'retrieve'})(request, pk=self.location_id)

        assert response.status_code == 200
        assert response.data.get("name") == self.location_expected_name

    def test_location_not_found(self):
        """Test that requesting a non-existent location returns 404."""
        non_existent_id = 99999
        request = self.factory.get(f"/api/location/{non_existent_id}")

        response = LocationViewSet.as_view({'get': 'retrieve'})(request, pk=non_existent_id)

        assert response.status_code == 404
        assert "detail" in response.data
        assert "No Location matches the given query." in str(response.data["detail"])
