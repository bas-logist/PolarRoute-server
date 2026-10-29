from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch
import warnings

from celery.exceptions import Ignore
from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.utils import timezone as django_timezone
import pytest
import yaml
from polar_route.exceptions import NoRouteFoundError

from polarrouteserver.celery import app
from polarrouteserver.route_api.models import VehicleMesh, EnvironmentMesh, Job, Mesh, Route, Vehicle
from polarrouteserver.route_api.tasks import (
    cleanup_meshes,
    cleanup_routes,
    create_and_calculate_route,
    import_new_meshes,
)
from polarrouteserver.route_api.utils import add_vehicle_to_environment_mesh, optimise_route
from .utils import add_test_vehicle_mesh_to_db, calculate_md5, create_test_vehicle, add_test_environment_mesh_to_db

class TestOptimiseRoute(TestCase):
    def setUp(self):
        self.start_point_name = "start point"
        self.end_point_name = "end point"
        self.mesh = add_test_vehicle_mesh_to_db()
        self.vehicle = create_test_vehicle()
        self.route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh,
            vehicle=self.vehicle,
            start_name=self.start_point_name,
            end_name=self.end_point_name,
        )

        assert isinstance(self.mesh, VehicleMesh)
        assert isinstance(self.vehicle, Vehicle)
        assert isinstance(self.route, Route)

    def test_optimise_route(self):
        """optimise_route should return a dictionary"""
        route_json = optimise_route(self.mesh.json, self.route)
        assert isinstance(route_json, list)
        assert route_json[0][0]["features"][0]["properties"]["from"] == self.start_point_name
        assert route_json[0][0]["features"][0]["properties"]["to"] == self.end_point_name
        assert route_json[0][0]["features"][0]["properties"]["objective_function"] == "traveltime"
        assert route_json[1][0]["features"][0]["properties"]["objective_function"] == "fuel"

        route = Route.objects.get(id=self.route.id)
        assert route.json == route_json
        assert isinstance(route.json_unsmoothed, list)
        assert route.json_unsmoothed[0][0]["features"][0]["properties"]["objective_function"] == "traveltime"
        assert route.json_unsmoothed[1][0]["features"][0]["properties"]["objective_function"] == "fuel"

    def test_out_of_mesh_error(self):
        """Test that out of mesh locations causes error to be returned"""
        with open(settings.TEST_MESH_PATH) as f:
            mesh = json.load(f)

        lat_min = mesh["config"]["mesh_info"]["region"]["lat_min"]
        lat_max = mesh["config"]["mesh_info"]["region"]["lat_max"]
        lon_min = mesh["config"]["mesh_info"]["region"]["long_min"]
        lon_max = mesh["config"]["mesh_info"]["region"]["long_max"]

        self.out_of_mesh_route = Route.objects.create(
            start_lat=lat_min-5, start_lon=lon_min-5,
            end_lat=abs(lat_max-lat_min)/2, end_lon=abs(lon_max-lon_min)/2,
            mesh=self.mesh,
            vehicle=self.vehicle
        )

        with pytest.raises(NoRouteFoundError, match="Invalid waypoints. No accessible source waypoints specified"):
            optimise_route(self.mesh.json, self.out_of_mesh_route)

    def test_stale_mesh_warning(self):
        # make the created date on the mesh older than today for this test
        self.mesh.created = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=1)
        self.mesh.save()
        # Use the task instead of the utility function for this test since the task handles mesh date warnings
        task = create_and_calculate_route.delay(self.route.id)
        task.get()  # Wait for completion
        route = Route.objects.get(id=self.route.id)
        assert "Latest available mesh from" in route.info["info"]

class TestTaskStatus(TransactionTestCase):

    def setUp(self):
        self.mesh = add_test_vehicle_mesh_to_db()
        self.vehicle = create_test_vehicle()
        self.route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh, vehicle=self.vehicle
        )

    def test_task_status(self):
        """Test that task object status is updated appropriately."""
        task = create_and_calculate_route.delay(self.route.id)
        assert task.state == "SUCCESS"

    def test_unsmoothed_route_creation(self):
        """Test that route calculation task created unsmoothed route as well as the main route."""
        _ = create_and_calculate_route.delay(self.route.id)

        route = Route.objects.get(id=self.route.id)

        assert route.json is not None
        assert route.json_unsmoothed is not None


    def test_out_of_mesh_error_causes_task_failure(self):
        """Check that an example error (out of mesh) results in the task status being updated correctly."""
        with open(settings.TEST_MESH_PATH) as f:
            mesh = json.load(f)
        
        lat_min = mesh["config"]["mesh_info"]["region"]["lat_min"]
        lat_max = mesh["config"]["mesh_info"]["region"]["lat_max"]
        lon_min = mesh["config"]["mesh_info"]["region"]["long_min"]
        lon_max = mesh["config"]["mesh_info"]["region"]["long_max"]

        self.out_of_mesh_route = Route.objects.create(
            start_lat=lat_min-5, start_lon=lon_min-5,
            end_lat=abs(lat_max-lat_min)/2, end_lon=abs(lon_max-lon_min)/2,
            mesh=self.mesh,
            vehicle=self.vehicle
        )

        with pytest.raises(AssertionError):
            task = create_and_calculate_route.delay(self.out_of_mesh_route.id)
            assert task.state == "FAILURE"

class TestImportNewMeshes(TestCase):

    def setUp(self):

        self.metadata_filename = "upload_metadata_test.yaml"
        self.metadata_filepath = Path(settings.MESH_DIR, self.metadata_filename)

        self.mesh_filenames = ["southern_test_mesh.vessel_20240807T091201.json",
                               "central_test_mesh.vessel.json"]
        
        dummy_mesh_json = [{
                "config": {
                    "mesh_info": {
                        "region": {
                            "lat_min": -90,
                            "lat_max": -45,
                            "long_min": -175,
                            "long_max": 175,
                            "start_time": "2024-08-04",
                            "end_time": "2024-08-06",
                            "cell_width": 5.0,
                            "cell_height": 2.5
            }}}},
            {
                "config": {
                    "mesh_info": {
                        "region": {
                            "lat_min": -60,
                            "lat_max": 65,
                            "long_min": -85,
                            "long_max": 10,
                            "start_time": "2024-08-04",
                            "end_time": "2024-08-06",
                            "cell_width": 5.0,
                            "cell_height": 2.5
            }}}}]

        for i, filename in enumerate(self.mesh_filenames):
            # write out gzipped file
            with gzip.open(Path(settings.MESH_DIR, filename+".gz"), 'wb') as f:
                f.write(json.dumps(dummy_mesh_json[i]).encode('utf-8'))
            # also write out non zipped file just for calclating md5
            with open(Path(settings.MESH_DIR, filename), 'w') as f:
                json.dump(dummy_mesh_json[i], f, indent=4)

        # create minimal test metadata file
        self.metadata = {
            "records": [
                {   
                    "filepath": str(Path(settings.MESH_DIR, self.mesh_filenames[0])),
                    "created": "20241016T154603",
                    "size": 123456,
                    "md5": calculate_md5(str(Path(settings.MESH_DIR, self.mesh_filenames[0]))),
                    "meshiphi": "2.1.13",
                    "latlong": {
                        "latmin": -80.0,
                        "latmax": -40.0,
                        "lonmin":-110.0,
                        "lonmax":  -5.0,
                    }
                },
                {   
                    "filepath": str(Path(settings.MESH_DIR, self.mesh_filenames[1])),
                    "created": "20241016T155252",
                    "size": 123456,
                    "md5": calculate_md5(str(Path(settings.MESH_DIR, self.mesh_filenames[1]))),
                    "meshiphi": "2.1.13",
                    "latlong": {
                        "latmin": -60.0,
                        "latmax":  65.0,
                        "lonmin": -85.0,
                        "lonmax":  10.0,
                    }
                },
            ]
        }

        with open(self.metadata_filepath, 'w') as f:
            yaml.dump(self.metadata, f)

        with open(self.metadata_filepath, 'rb') as f_in:
            with gzip.open(Path(settings.MESH_DIR, self.metadata_filename+".gz"), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)


    def tearDown(self):
        # cleanup files created for testing
        for filename in self.mesh_filenames + [self.metadata_filename]:
            os.remove(Path(settings.MESH_DIR, filename))
            os.remove(Path(settings.MESH_DIR, filename+".gz"))
        

    def test_import_new_meshes(self):
        """Test importing EnvironmentMeshes (meshes without vessel configuration)"""
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            meshes_added = import_new_meshes()

        assert len(meshes_added) ==  len(self.mesh_filenames)

        for mesh in meshes_added:
            mesh_obj = EnvironmentMesh.objects.get(id=mesh["id"])
            assert mesh_obj.id  == mesh["id"]
            assert mesh_obj.md5 == mesh["md5"]
            assert mesh["type"] == "EnvironmentMesh"

        all_meshes = EnvironmentMesh.objects.all()

        # run same meshes again and test not added again
        meshes_added = import_new_meshes()
        assert len(meshes_added) == 0

        all_meshes2 = EnvironmentMesh.objects.all()
        assert list(all_meshes) == list(all_meshes2)

    def write_metadata(self):
        with gzip.open(Path(settings.MESH_DIR, self.metadata_filename + ".gz"), "wb") as f:
            f.write(yaml.dump(self.metadata).encode("utf-8"))

    def test_mesh_with_wrong_md5_is_skipped(self):
        """A mesh whose md5 differs from the one in the metadata (e.g. a filename clash) is not imported."""
        self.metadata["records"][0]["md5"] = "0" * 32
        self.write_metadata()

        meshes_added = import_new_meshes()

        assert [m["name"] for m in meshes_added] == [self.mesh_filenames[1]]
        assert Mesh.objects.count() == 1

    def test_unreadable_mesh_file_is_skipped(self):
        """A file which is still transferring doesn't stop the others being imported."""
        with open(Path(settings.MESH_DIR, self.mesh_filenames[0] + ".gz"), "wb") as f:
            f.write(b"not a gzip file")

        meshes_added = import_new_meshes()

        assert [m["name"] for m in meshes_added] == [self.mesh_filenames[1]]

    def test_truncated_mesh_file_is_skipped(self):
        path = Path(settings.MESH_DIR, self.mesh_filenames[0] + ".gz")
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])

        meshes_added = import_new_meshes()

        assert [m["name"] for m in meshes_added] == [self.mesh_filenames[1]]

    def test_incomplete_metadata_record_is_skipped(self):
        del self.metadata["records"][0]["latlong"]
        self.write_metadata()

        meshes_added = import_new_meshes()

        assert [m["name"] for m in meshes_added] == [self.mesh_filenames[1]]

    def test_json_which_is_not_a_mesh_is_skipped(self):
        other = "other.json"
        with gzip.open(Path(settings.MESH_DIR, other + ".gz"), "wb") as f:
            f.write(json.dumps({"not": "a mesh"}).encode("utf-8"))
        self.metadata["records"].insert(
            0, {**self.metadata["records"][0], "filepath": str(Path(settings.MESH_DIR, other))}
        )
        self.write_metadata()

        try:
            meshes_added = import_new_meshes()
        finally:
            os.remove(Path(settings.MESH_DIR, other + ".gz"))

        assert sorted(m["name"] for m in meshes_added) == sorted(self.mesh_filenames)

    def test_import_vehicle_meshes(self):
        """Test importing VehicleMeshes (meshes with vessel configuration)"""
        
        # Create mesh filenames that indicate vehicle meshes
        vehicle_mesh_filenames = ["test_vehicle_mesh_1.vessel.json", "test_vehicle_mesh_2.vessel.json"]
        
        # Create dummy mesh JSON with vessel configuration
        dummy_vehicle_mesh_json = [
            {
                "config": {
                    "mesh_info": {
                        "region": {
                            "lat_min": -90,
                            "lat_max": -45,
                            "long_min": -175,
                            "long_max": 175,
                            "start_time": "2024-08-04",
                            "end_time": "2024-08-06",
                            "cell_width": 5.0,
                            "cell_height": 2.5
                        }
                    },
                    "vessel_info": {
                        "vessel_type": "TEST_VESSEL_1",
                        "max_speed": 20.0,
                        "unit": "km/hr",
                        "beam": 15.0,
                        "hull_type": "slender"
                    }
                }
            },
            {
                "config": {
                    "mesh_info": {
                        "region": {
                            "lat_min": -60,
                            "lat_max": 65,
                            "long_min": -85,
                            "long_max": 10,
                            "start_time": "2024-08-04",
                            "end_time": "2024-08-06",
                            "cell_width": 5.0,
                            "cell_height": 2.5
                        }
                    },
                    "vessel_info": {
                        "vessel_type": "TEST_VESSEL_2", 
                        "max_speed": 25.0,
                        "unit": "km/hr",
                        "beam": 18.0,
                        "hull_type": "slender"
                    }
                }
            }
        ]

        # Write out the vehicle mesh files
        for i, filename in enumerate(vehicle_mesh_filenames):
            # write out gzipped file
            with gzip.open(Path(settings.MESH_DIR, filename+".gz"), 'wb') as f:
                f.write(json.dumps(dummy_vehicle_mesh_json[i]).encode('utf-8'))
            # also write out non zipped file just for calculating md5
            with open(Path(settings.MESH_DIR, filename), 'w') as f:
                json.dump(dummy_vehicle_mesh_json[i], f, indent=4)

        # Create metadata for vehicle meshes
        vehicle_metadata = {
            "records": [
                {   
                    "filepath": str(Path(settings.MESH_DIR, vehicle_mesh_filenames[0])),
                    "created": "20241016T160000",
                    "size": 123456,
                    "md5": calculate_md5(str(Path(settings.MESH_DIR, vehicle_mesh_filenames[0]))),
                    "meshiphi": "2.1.13",
                    "latlong": {
                        "latmin": -80.0,
                        "latmax": -40.0,
                        "lonmin":-110.0,
                        "lonmax":  -5.0,
                    }
                },
                {   
                    "filepath": str(Path(settings.MESH_DIR, vehicle_mesh_filenames[1])),
                    "created": "20241016T160100",
                    "size": 123456,
                    "md5": calculate_md5(str(Path(settings.MESH_DIR, vehicle_mesh_filenames[1]))),
                    "meshiphi": "2.1.13",
                    "latlong": {
                        "latmin": -60.0,
                        "latmax":  65.0,
                        "lonmin": -85.0,
                        "lonmax":  10.0,
                    }
                },
            ]
        }

        vehicle_metadata_filename = "upload_metadata_vehicle_test.yaml"
        vehicle_metadata_filepath = Path(settings.MESH_DIR, vehicle_metadata_filename)

        with open(vehicle_metadata_filepath, 'w') as f:
            yaml.dump(vehicle_metadata, f)

        with open(vehicle_metadata_filepath, 'rb') as f_in:
            with gzip.open(Path(settings.MESH_DIR, vehicle_metadata_filename+".gz"), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        try:
            # Test importing vehicle meshes
            with warnings.catch_warnings():
                warnings.simplefilter("error", UserWarning)
                meshes_added = import_new_meshes()

            assert len(meshes_added) == len(vehicle_mesh_filenames)

            for mesh in meshes_added:
                mesh_obj = VehicleMesh.objects.get(id=mesh["id"])
                assert mesh_obj.id == mesh["id"]
                assert mesh_obj.md5 == mesh["md5"]
                assert mesh["type"] == "VehicleMesh"
                # Verify vehicle was created
                assert mesh_obj.vehicle is not None
                assert mesh_obj.vehicle.vessel_type in ["TEST_VESSEL_1", "TEST_VESSEL_2"]

            # Verify vehicles were created in database
            vessel_1 = Vehicle.objects.get(vessel_type="TEST_VESSEL_1")
            vessel_2 = Vehicle.objects.get(vessel_type="TEST_VESSEL_2")
            assert vessel_1.max_speed == 20.0
            assert vessel_2.max_speed == 25.0

        finally:
            # Cleanup vehicle mesh files
            for filename in vehicle_mesh_filenames + [vehicle_metadata_filename]:
                try:
                    os.remove(Path(settings.MESH_DIR, filename))
                    os.remove(Path(settings.MESH_DIR, filename+".gz"))
                except FileNotFoundError:
                    pass


@pytest.mark.django_db
class TestCreateAndCalculateRoute:
    """Tests for the create_and_calculate_route task."""

    def setup_method(self):
        self.sda = Vehicle.objects.create(
            vessel_type="SDA",
            max_speed=30,
            unit="km/hr",
            beam=10,
            hull_type="slender",
            force_limit=100000,
            max_ice_conc=80,
            min_depth=10,
        )
        self.env_mesh = add_test_environment_mesh_to_db()

    def make_route(self, **kwargs):
        defaults = dict(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9,
            mesh=self.env_mesh, vehicle=self.sda,
        )
        return Route.objects.create(**(defaults | kwargs))

    def test_vehicle_mesh_is_built_from_environment_mesh(self):
        route = self.make_route()
        assert not VehicleMesh.objects.exists()

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert route.calculated is not None
        assert route.json is not None
        assert route.mesh_id == self.env_mesh.id
        vehicle_mesh = VehicleMesh.objects.get()
        assert vehicle_mesh.environment_mesh_id == self.env_mesh.id
        assert vehicle_mesh.vehicle_id == "SDA"

    def test_vehicle_mesh_used_is_recorded_on_the_route(self):
        route = self.make_route()

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert route.vehicle_mesh_id == VehicleMesh.objects.get().id
        assert route.mesh_id == self.env_mesh.id

    def test_missing_ice_data_is_warned_about_on_the_route(self):
        route = self.make_route()

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert "have no sea ice concentration data" in route.info["info"]

    def test_existing_vehicle_mesh_is_reused(self):
        first = self.make_route()
        second = self.make_route()

        create_and_calculate_route.delay(first.id)
        create_and_calculate_route.delay(second.id)

        assert VehicleMesh.objects.count() == 1

    def test_battery_vehicle_is_optimised_for_battery_use(self):
        boaty = Vehicle.objects.create(
            vessel_type="BoatyMcBoatFace", max_speed=3.6, unit="km/hr",
            max_ice_conc=10, min_depth=10,
        )
        route = self.make_route(vehicle=boaty)

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert route.json is not None, route.info
        objectives = [r[0]["features"][0]["properties"]["objective_function"] for r in route.json]
        assert objectives == ["traveltime", "battery"]

    def test_vehicle_mesh_for_other_vehicle_is_used_through_its_environment_mesh(self):
        sda_mesh = add_vehicle_to_environment_mesh(self.env_mesh, self.sda)
        boaty = Vehicle.objects.create(
            vessel_type="BoatyMcBoatFace", max_speed=3.6, unit="km/hr",
            max_ice_conc=10, min_depth=10,
        )
        route = self.make_route(mesh=sda_mesh, vehicle=boaty)

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert route.json is not None, route.info
        assert VehicleMesh.objects.filter(
            environment_mesh=self.env_mesh, vehicle=boaty
        ).exists()

    def test_unknown_vessel_type_is_an_error_on_the_route(self):
        unknown = Vehicle.objects.create(
            vessel_type="NOT_A_KNOWN_VESSEL", max_speed=10.0, unit="km/hr"
        )
        route = self.make_route(vehicle=unknown)

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert "not in known list of vessels" in route.info["error"]
        assert route.json is None

    def test_route_without_mesh_is_an_error_on_the_route(self):
        route = self.make_route(mesh=None)

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert "error" in route.info
        assert route.json is None

    def test_route_without_vehicle_is_an_error_on_the_route(self):
        route = self.make_route(vehicle=None)

        create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert "error" in route.info
        assert route.json is None

    def test_inaccessible_route_is_retried_on_backup_mesh(self):
        backup_mesh = add_test_environment_mesh_to_db()
        route = self.make_route()

        with patch(
            "polarrouteserver.route_api.tasks.optimise_route",
            side_effect=[ValueError("Inaccessible. No routes found."), []],
        ) as mock_optimise:
            create_and_calculate_route.delay(route.id, backup_mesh_ids=[backup_mesh.id])

        assert mock_optimise.call_count == 2
        route.refresh_from_db()
        assert route.mesh_id == backup_mesh.id
        assert Job.objects.filter(route=route).count() == 1

    def test_inaccessible_route_without_backup_mesh_is_an_error(self):
        route = self.make_route()

        with patch(
            "polarrouteserver.route_api.tasks.optimise_route",
            side_effect=ValueError("Inaccessible. No routes found."),
        ):
            create_and_calculate_route.delay(route.id)

        route.refresh_from_db()
        assert "Inaccessible" in route.info["error"]
        assert not Job.objects.filter(route=route).exists()


@pytest.mark.django_db
class TestVehicleMeshCreationWorkflow:
    """Test which mesh create_and_calculate_route uses for imported vehicle meshes."""

    def setup_method(self):
        self.vehicle_test = create_test_vehicle()
        self.env_mesh = add_test_environment_mesh_to_db()

    def test_route_with_matching_vehicle_mesh_uses_existing(self):
        """Test that route with correct VehicleMesh uses existing mesh without creating new one."""
        # Create correct VehicleMesh for TEST_VESSEL
        correct_vehicle_mesh = add_test_vehicle_mesh_to_db()
        
        initial_mesh_count = VehicleMesh.objects.count()
        
        # Create route with correct VehicleMesh
        route = Route.objects.create(
            start_lat=-40.0,
            start_lon=-40.0,
            end_lat=40.0,
            end_lon=40.0, 
            mesh=correct_vehicle_mesh,
            vehicle=self.vehicle_test,
            requested=django_timezone.now()
        )
        
        # Run task - should use existing mesh
        result = create_and_calculate_route.delay(route.id)
        _ = result.get(timeout=30)
        
        # Verify route was calculated
        route.refresh_from_db()
        assert route.calculated is not None
        assert route.json is not None
        
        # Verify no new VehicleMesh was created
        final_mesh_count = VehicleMesh.objects.count()
        assert final_mesh_count == initial_mesh_count
        
        # Verify route still uses same mesh
        assert route.mesh.id == correct_vehicle_mesh.id


@pytest.mark.django_db  
class TestTaskErrorHandling:
    """Test error handling in tasks."""

    def test_create_route_with_invalid_route_id(self):
        """Test task behavior with invalid route ID."""
        with pytest.raises(Route.DoesNotExist):
            result = create_and_calculate_route.delay(99999)
            result.get(timeout=10)

    def test_import_meshes_no_metadata_file(self):
        """Test import_new_meshes when no metadata file exists."""
        result = import_new_meshes.delay()
        meshes_added = result.get(timeout=10)
        
        # Should return None when no metadata file exists
        assert meshes_added is None


class TestRouteCleanup(TestCase):

    def tearDown(self):
        # return these settings to default after tests are run to avoid settings leakage between tests
        settings.CLEANUP_ROUTES = False
        settings.CLEANUP_MESHES = False

    def test_settings_catch(self):
        "Test that with default settings, CLEANUP_ROUTES=False, that on calling the task, deletion is prevented"
        with pytest.raises(Exception):
            cleanup_routes()

    def test_cleanup_routes(self):
        self.mesh = add_test_environment_mesh_to_db()
        self.new_route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh
        )
        self.new_route.calculated = datetime.now().replace(tzinfo=timezone.utc)
        self.new_route.save()

        self.old_route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh
        )
        self.old_route.calculated = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        self.old_route.save()

        # start by checking number of routes in db
        assert len(Route.objects.all()) == 2

        # enable routes cleanup, but with threshold age higher than all the available routes
        settings.CLEANUP_ROUTES = True
        settings.CLEANUP_ROUTES_DAYS = 20
        cleanup_routes()
        assert len(Route.objects.all()) == 2

        # set the threshold between our two routes, run cleanup and check that only one is left
        settings.CLEANUP_ROUTES_DAYS = 5
        cleanup_routes()
        assert len(Route.objects.all()) == 1

        # add another route to the db and protect it
        self.old_route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh, protect=True
        )
        self.old_route.calculated = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        self.old_route.save()
        assert len(Route.objects.all()) == 2
        cleanup_routes()
        assert len(Route.objects.all()) == 2


class TestMeshCleanup(TestCase):

    def tearDown(self):
        # return these settings to default after tests are run to avoid settings leakage between tests
        settings.CLEANUP_ROUTES = False
        settings.CLEANUP_MESHES = False

    def test_settings_catch(self):
        "Test that with default settings, CLEANUP_MESHES=False, that on calling the task, deletion is prevented"
        with pytest.raises(Exception):
            cleanup_meshes()

    def test_cleanup_meshes(self):
        self.new_mesh = add_test_environment_mesh_to_db()
        self.old_mesh = add_test_environment_mesh_to_db()
        self.old_mesh.created = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        self.old_mesh.save()

        # start by checking number of meshes in db
        assert len(Mesh.objects.all()) == 2

        # enable mesh cleanup, but with threshold age higher than all the available meshes
        settings.CLEANUP_MESHES = True
        settings.CLEANUP_MESHES_DAYS = 20
        cleanup_meshes()
        assert len(Mesh.objects.all()) == 2

        # set the threshold between our two meshes, run cleanup and check that only one is left
        settings.CLEANUP_MESHES_DAYS = 5
        cleanup_meshes()
        assert len(Mesh.objects.all()) == 1

        # add another mesh to the db and protect it
        self.old_mesh = add_test_environment_mesh_to_db()
        self.old_mesh.created = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        self.old_mesh.protect = True
        self.old_mesh.save()
        assert len(Mesh.objects.all()) == 2
        cleanup_meshes()
        assert len(Mesh.objects.all()) == 2

    def test_protected_vehicle_mesh_protects_its_environment_mesh(self):
        old = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        vehicle_mesh = add_test_vehicle_mesh_to_db()
        environment_mesh = vehicle_mesh.environment_mesh
        EnvironmentMesh.objects.filter(id=environment_mesh.id).update(created=old)
        VehicleMesh.objects.filter(id=vehicle_mesh.id).update(created=old, protect=True)

        settings.CLEANUP_MESHES = True
        settings.CLEANUP_MESHES_DAYS = 5
        cleanup_meshes()

        assert EnvironmentMesh.objects.filter(id=environment_mesh.id).exists()
        assert VehicleMesh.objects.filter(id=vehicle_mesh.id).exists()

        VehicleMesh.objects.filter(id=vehicle_mesh.id).update(protect=False)
        cleanup_meshes()

        assert not Mesh.objects.exists()

    def test_cleanup_removes_environment_and_vehicle_meshes(self):
        old_vehicle_mesh = add_test_vehicle_mesh_to_db()
        old_env_mesh = old_vehicle_mesh.environment_mesh
        old_env_mesh.created = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        old_env_mesh.save()
        old_vehicle_mesh.created = old_env_mesh.created
        old_vehicle_mesh.save()
        assert Mesh.objects.count() == 2

        settings.CLEANUP_MESHES = True
        settings.CLEANUP_MESHES_DAYS = 5
        cleanup_meshes()

        assert Mesh.objects.count() == 0
        assert not EnvironmentMesh.objects.exists()
        assert not VehicleMesh.objects.exists()
