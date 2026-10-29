import datetime
import hashlib
import json
from unittest.mock import patch, PropertyMock
import uuid

import celery
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from haversine import inverse_haversine, Unit, Direction
import pytest

from polarrouteserver.route_api.models import EnvironmentMesh, Mesh, VehicleMesh, Vehicle, Job, Route
from polarrouteserver.route_api.utils import check_missing_ice_data, evaluate_route, get_vehicle_mesh, route_exists, select_mesh, select_mesh_for_route_evaluation, check_mesh_data
from .utils import add_test_environment_mesh_to_db, add_test_vehicle_mesh_to_db, create_test_vehicle

class TestRouteExists(TestCase):
    "Test function for checking for existing routes"

    def setUp(self):
        "Create a route in the test database"

        self.mesh = add_test_vehicle_mesh_to_db()
        self.vehicle = self.mesh.vehicle

        # Verify we're working with correct types
        assert isinstance(self.mesh, VehicleMesh)
        assert isinstance(self.vehicle, Vehicle)

        self.start_lat = 64.16
        self.start_lon = -21.99
        self.end_lat = 78.24
        self.end_lon = 15.61

        self.route = Route.objects.create(
            calculated=timezone.now(),
            start_lat=self.start_lat,
            start_lon=self.start_lon,
            end_lat=self.end_lat,
            end_lon=self.end_lon,
            mesh=self.mesh,
            vehicle=self.vehicle
        )

        self.job = Job.objects.create(id=uuid.uuid1(),route=self.route)

    def test_route_exists(self):
        "Test case where exact requested route exists"
        with patch(
            "polarrouteserver.route_api.views.AsyncResult.state", new_callable=PropertyMock
        ) as mock_job_status:
            mock_job_status.return_value = celery.states.SUCCESS
        
            route = route_exists(
                self.mesh,
                start_lat=self.start_lat,
                start_lon=self.start_lon,
                end_lat=self.end_lat,
                end_lon=self.end_lon,
                vehicle=self.vehicle,
            )
        assert route == self.route

    def test_failed_route_exists(self):
        "Test case where exact requested route exists, but has failed."
        with patch(
            "polarrouteserver.route_api.views.AsyncResult.state", new_callable=PropertyMock
        ) as mock_job_status:
            mock_job_status.return_value = celery.states.FAILURE
        
            route = route_exists(
                self.mesh,
                start_lat=self.start_lat,
                start_lon=self.start_lon,
                end_lat=self.end_lat,
                end_lon=self.end_lon,
                vehicle=self.vehicle,
            )
        assert route == None

    def test_no_route_exists(self):
        "Test case where no similar route exists"

        with patch(
            "polarrouteserver.route_api.views.AsyncResult.state", new_callable=PropertyMock
        ) as mock_job_status:
            mock_job_status.return_value = celery.states.SUCCESS

            route = route_exists(
                self.mesh,
                start_lat=0,
                start_lon=0,
                end_lat=0,
                end_lon=0,
                vehicle=self.vehicle,
            )
        assert route is None

    def test_route_for_other_vehicle_not_returned(self):
        "A route calculated for one vehicle is not returned for another vehicle."

        other_vehicle = Vehicle.objects.create(
            vessel_type="OTHER_VESSEL", max_speed=10.0, unit="km/hr"
        )

        route = route_exists(
            self.mesh,
            start_lat=self.start_lat,
            start_lon=self.start_lon,
            end_lat=self.end_lat,
            end_lon=self.end_lon,
            vehicle=other_vehicle,
        )
        assert route is None

    def test_exact_route_returned(self):
        """Test exact route returned if other nearby routes exist"""

        # use inverse haversine method to create points at specified distance from start and end points
        in_tolerance_start = inverse_haversine(
            (self.start_lat, self.start_lon),
            0.9 * settings.WAYPOINT_DISTANCE_TOLERANCE,
            Direction.NORTH,
            unit=Unit.NAUTICAL_MILES,
        )
        in_tolerance_end = inverse_haversine(
            (self.end_lat, self.end_lon),
            0.9 * settings.WAYPOINT_DISTANCE_TOLERANCE,
            Direction.NORTH,
            unit=Unit.NAUTICAL_MILES,
        )

        # create another nearby route
        nearby_route = Route.objects.create(
            calculated=timezone.now(),
            start_lat=in_tolerance_start[0],
            start_lon=in_tolerance_start[1],
            end_lat=in_tolerance_end[0],
            end_lon=in_tolerance_end[1],
            mesh=self.mesh,
            vehicle=self.vehicle
        )

        Job.objects.create(id=uuid.uuid1(), route=nearby_route)

        with patch(
            "polarrouteserver.route_api.views.AsyncResult.state", new_callable=PropertyMock
        ) as mock_job_status:
            mock_job_status.return_value = celery.states.SUCCESS

            route = route_exists(
                self.mesh,
                start_lat=self.start_lat,
                start_lon=self.start_lon,
                end_lat=self.end_lat,
                end_lon=self.end_lon,
                vehicle=self.vehicle,
            )
        assert route == self.route

        ### Test that closest of multiple routes is the one returned if no exact route is found
        # remove the exact route
        route.delete()

        in_tolerance_start = inverse_haversine(
            (self.start_lat, self.start_lon),
            0.8 * settings.WAYPOINT_DISTANCE_TOLERANCE,
            Direction.NORTH,
            unit=Unit.NAUTICAL_MILES,
        )
        in_tolerance_end = inverse_haversine(
            (self.end_lat, self.end_lon),
            0.8 * settings.WAYPOINT_DISTANCE_TOLERANCE,
            Direction.NORTH,
            unit=Unit.NAUTICAL_MILES,
        )

        # create another nearby route
        closest_route = Route.objects.create(
            calculated=timezone.now(),
            start_lat=in_tolerance_start[0],
            start_lon=in_tolerance_start[1],
            end_lat=in_tolerance_end[0],
            end_lon=in_tolerance_end[1],
            mesh=self.mesh,
            vehicle=self.vehicle
        )

        Job.objects.create(id=uuid.uuid1(), route=closest_route)

        with patch(
            "polarrouteserver.route_api.views.AsyncResult.state", new_callable=PropertyMock
        ) as mock_job_status:
            mock_job_status.return_value = celery.states.SUCCESS

            # search for route with no exact match
            route = route_exists(
                self.mesh,
                start_lat=self.start_lat,
                start_lon=self.start_lon,
                end_lat=self.end_lat,
                end_lon=self.end_lon,
                vehicle=self.vehicle,
            )
        assert route == closest_route

class TestSelectMesh(TestCase):

    def setUp(self):
        # create some meshes in the database

        self.southern_mesh = EnvironmentMesh.objects.create(
            name = "southern_test_mesh.vessel.json",
            md5 = hashlib.md5("dummy_hashable_string".encode('utf-8')).hexdigest(),
            meshiphi_version = "2.1.13",
            valid_date_start = timezone.now().date() - datetime.timedelta(days=3),
            valid_date_end = timezone.now().date(),
            created = datetime.datetime.now(datetime.UTC),
            lat_min =  -80.0,
            lat_max =  -40.0,
            lon_min = -110.0,
            lon_max =   -5.0
        )

    def test_select_mesh(self):
        meshes = select_mesh(
            start_lat = -60,
            start_lon = -55,
            end_lat   = -80,
            end_lon   = -110
        )
        assert [m.id for m in meshes] == [self.southern_mesh.id]

        # test that when no containing mesh available, the result is None
        assert select_mesh(
            start_lat = -90,
            start_lon = -55,
            end_lat   = -80,
            end_lon   = -110
        ) == None

    def test_smallest_mesh(self):
        self.smallest_mesh = EnvironmentMesh.objects.create(
            name = "smallest_test_mesh.vessel.json",
            md5 = hashlib.md5("dummy_hashable_string".encode('utf-8')).hexdigest(),
            meshiphi_version = "2.1.13",
            valid_date_start = timezone.now().date() - datetime.timedelta(days=3),
            valid_date_end = timezone.now().date(),
            created = datetime.datetime.now(datetime.UTC),
            lat_min =  -80.0,
            lat_max =  -56.0,
            lon_min = -115.0,
            lon_max =    0.0,
        )

        self.smaller_mesh = EnvironmentMesh.objects.create(
            name = "smaller_test_mesh.vessel.json",
            md5 = hashlib.md5("dummy_hashable_string".encode('utf-8')).hexdigest(),
            meshiphi_version = "2.1.13",
            valid_date_start = timezone.now().date() - datetime.timedelta(days=3),
            valid_date_end = timezone.now().date(),
            created = datetime.datetime.now(datetime.UTC),
            lat_min =  -85.0,
            lat_max =  -60.0,
            lon_min = -117.0,
            lon_max =    0.0,
        )

        # check that we've actually made a smaller mesh
        assert self.smaller_mesh.size < self.southern_mesh.size
        assert self.smallest_mesh.size < self.smaller_mesh.size

        meshes = select_mesh(
            start_lat = -60,
            start_lon = -55,
            end_lat   = -80,
            end_lon   = -110
        )
        assert [m.id for m in meshes] == [
            self.smallest_mesh.id,
            self.smaller_mesh.id,
            self.southern_mesh.id,
        ]

    def test_select_mesh_candidates(self):
        """Only environment meshes and imported vehicle meshes of the requested vehicle are candidates."""

        vehicle = Vehicle.objects.create(vessel_type="V1", max_speed=10.0, unit="km/hr")
        other_vehicle = Vehicle.objects.create(vessel_type="V2", max_speed=10.0, unit="km/hr")
        region = dict(
            valid_date_start=timezone.now().date(),
            valid_date_end=timezone.now().date(),
            created=datetime.datetime.now(datetime.UTC),
            lat_min=-80.0, lat_max=-40.0, lon_min=-110.0, lon_max=-5.0,
        )
        # built from an environment mesh: found through the environment mesh instead
        derived = VehicleMesh.objects.create(
            name="derived", md5="derived", vehicle=vehicle,
            environment_mesh=self.southern_mesh, **region
        )
        # imported, so with no environment mesh
        imported = VehicleMesh.objects.create(name="imported", md5="imported", vehicle=vehicle, **region)
        VehicleMesh.objects.create(name="other", md5="other", vehicle=other_vehicle, **region)

        coords = dict(start_lat=-60, start_lon=-55, end_lat=-80, end_lon=-110)

        ids = [m.id for m in select_mesh(**coords)]
        assert ids == [self.southern_mesh.id]

        ids = [m.id for m in select_mesh(**coords, vehicle_type="V1")]
        assert sorted(ids) == sorted([self.southern_mesh.id, imported.id])
        assert derived.id not in ids

    def test_select_mesh_prefers_imported_vehicle_mesh_of_same_size(self):
        """Imported vehicle meshes don't need to be built, so come first whichever was added first."""

        vehicle = Vehicle.objects.create(vessel_type="V1", max_speed=10.0, unit="km/hr")
        region = dict(
            valid_date_start=self.southern_mesh.valid_date_start,
            valid_date_end=self.southern_mesh.valid_date_end,
            created=self.southern_mesh.created,
            lat_min=self.southern_mesh.lat_min, lat_max=self.southern_mesh.lat_max,
            lon_min=self.southern_mesh.lon_min, lon_max=self.southern_mesh.lon_max,
        )
        coords = dict(start_lat=-60, start_lon=-55, end_lat=-80, end_lon=-110)

        # the environment mesh was added first
        imported = VehicleMesh.objects.create(name="imported", md5="imported", vehicle=vehicle, **region)
        meshes = select_mesh(**coords, vehicle_type="V1")
        assert [m.id for m in meshes] == [imported.id, self.southern_mesh.id]

        # the vehicle mesh was added first
        Mesh.objects.all().delete()
        imported = VehicleMesh.objects.create(name="imported", md5="imported", vehicle=vehicle, **region)
        environment = EnvironmentMesh.objects.create(name="environment", md5="environment", **region)
        meshes = select_mesh(**coords, vehicle_type="V1")
        assert [m.id for m in meshes] == [imported.id, environment.id]

    def test_select_mesh_latest_date_only(self):
        EnvironmentMesh.objects.create(
            name="older", md5="older",
            valid_date_start=timezone.now().date(), valid_date_end=timezone.now().date(),
            created=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
            lat_min=-80.0, lat_max=-56.0, lon_min=-115.0, lon_max=0.0,
        )
        meshes = select_mesh(start_lat=-60, start_lon=-55, end_lat=-80, end_lon=-110)
        assert [m.id for m in meshes] == [self.southern_mesh.id]

    def test_select_mesh_for_route_evaluation(self):

        self.mesh_for_evaluation = add_test_vehicle_mesh_to_db()

        with open(settings.TEST_ROUTE_PATH) as fp:
            self.route_json = json.load(fp)

        meshes = select_mesh_for_route_evaluation(self.route_json, "TEST_VESSEL")
        assert [m.id for m in meshes] == [self.mesh_for_evaluation.environment_mesh.id]

@pytest.mark.django_db
def test_evaluate_route():
    vehicle_mesh = add_test_vehicle_mesh_to_db()

    with open(settings.TEST_ROUTE_PATH) as fp:
        route_json = json.load(fp)

    meshes = select_mesh_for_route_evaluation(route_json, "TEST_VESSEL")
    assert meshes is not None

    # the vehicle mesh already exists for the environment mesh and vehicle, so it is found
    mesh = get_vehicle_mesh(meshes[0], vehicle_mesh.vehicle)
    assert mesh.id == vehicle_mesh.id

    result = evaluate_route(route_json, mesh)
    assert isinstance(result, dict)


class TestMeshDataMessage(TestCase):

    def test_no_missing_data_message(self):
        mesh = add_test_environment_mesh_to_db()
        mesh.json['config']['mesh_info']['data_sources'] = [
            {"loader": "GEBCO", "params": {"files": ["1"]}},
            {"loader": "amsr", "params": {"files": ["1", "2", "3"]}},
            {"loader": "duacs_currents", "params": {"files": ["1", "2", "3"]}},
            {"loader": "thickness", "params": {"files": [""]}},
            {"loader": "density", "params": {"files": [""]}},
        ]
        assert check_mesh_data(mesh) == ""

    def test_missing_data_message(self):
        mesh = add_test_environment_mesh_to_db()
        mesh.json['config']['mesh_info']['data_sources'] = [
            {"loader": "amsr", "params": {"files": ["1", "2", "3"]}},
            {"loader": "duacs_currents", "params": {"files": ["1", "2", "3"]}},
            {"loader": "thickness", "params": {"files": [""]}},
            {"loader": "density", "params": {"files": [""]}},
        ]
        assert check_mesh_data(mesh) == "Warning: This mesh is missing data on the following parameters: bathymetry.\n"

    def test_unexpected_data_length_message(self):
        mesh = add_test_environment_mesh_to_db()
        mesh.json['config']['mesh_info']['data_sources'] = [
            {"loader": "GEBCO", "params": {"files": ["1"]}},
            {"loader": "amsr", "params": {"files": ["1", "2"]}},
            {"loader": "duacs_currents", "params": {"files": ["1", "2", "3"]}},
            {"loader": "thickness", "params": {"files": [""]}},
            {"loader": "density", "params": {"files": [""]}},
        ]
        assert check_mesh_data(mesh) == "Warning: 2 of expected 3 days' data available for sea ice concentration.\n"


class TestMissingIceDataMessage(TestCase):

    def mesh_with_cells(self, cells):
        mesh = add_test_environment_mesh_to_db()
        mesh.json["cellboxes"] = cells
        return mesh

    def test_no_missing_ice_data(self):
        mesh = self.mesh_with_cells([{"SIC": 0.0}, {"SIC": 50.0}])
        assert check_missing_ice_data(mesh) == ""

    def test_missing_ice_data_message(self):
        mesh = self.mesh_with_cells(
            [{"SIC": None}, {"SIC": float("nan")}, {}, {"SIC": 12.5}]
        )
        assert check_missing_ice_data(mesh) == (
            "Warning: 3 of 4 sea cells have no sea ice concentration data, "
            "these are treated as ice-free.\n"
        )

    def test_land_cells_are_not_counted(self):
        mesh = self.mesh_with_cells([{"SIC": None, "land": True}, {"SIC": 10.0, "land": False}])
        assert check_missing_ice_data(mesh) == ""
