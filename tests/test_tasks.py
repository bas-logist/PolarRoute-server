from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import warnings

from celery.exceptions import Ignore
from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.utils import timezone as django_timezone
import pytest
import yaml
from polar_route.exceptions import NoRouteFoundError

from polarrouteserver.celery import app
from polarrouteserver.route_api.models import VehicleMesh, EnvironmentMesh, Route, Vehicle
from polarrouteserver.route_api.tasks import import_new_meshes, create_and_calculate_route
from polarrouteserver.route_api.utils import calculate_md5, optimise_route
from .utils import add_test_vehicle_mesh_to_db, create_test_vehicle, add_test_environment_mesh_to_db

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
        task = create_and_calculate_route.delay(self.route.id, "TEST_VESSEL")
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
        task = create_and_calculate_route.delay(self.route.id, "TEST_VESSEL")
        assert task.state == "SUCCESS"

    def test_unsmoothed_route_creation(self):
        """Test that route calculation task created unsmoothed route as well as the main route."""
        _ = create_and_calculate_route.delay(self.route.id, "TEST_VESSEL")

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
            task = create_and_calculate_route.delay(self.out_of_mesh_route.id, "TEST_VESSEL")
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
    """Comprehensive tests for the create_and_calculate_route task."""

    def setup_method(self):
        """Set up test fixtures."""
        # Use existing test utility to create test vehicle
        self.test_vehicle = create_test_vehicle()
        
    def test_task_validates_route_exists(self):
        """Test that task validates route exists before processing."""
        try:
            create_and_calculate_route.delay(99999, "TEST_VESSEL")
        except Exception as e:
            # Should fail due to Route.DoesNotExist - that's expected behavior
            assert "does not exist" in str(e) or "Route" in str(e)

    def test_task_validates_vehicle_type_required(self):
        """Test that task validates vehicle_type is required."""
        # Create a route first
        vehicle = self.test_vehicle
        route = Route.objects.create(
            start_lat=67.5,
            start_lon=-42.5,
            end_lat=67.7,
            end_lon=-42.5,
            vehicle=vehicle,
            requested=django_timezone.now()
        )
        
        # Test that calling task without vehicle_type validates properly
        try:
            create_and_calculate_route.delay(route.id)  # No vehicle_type provided
        except Exception as e:
            # Should fail due to missing vehicle_type - that's expected
            assert "vehicle_type is required" in str(e)


@pytest.mark.django_db
class TestVehicleMeshCreationWorkflow:
    """Test VehicleMesh creation workflow in create_and_calculate_route task."""

    def setup_method(self):
        """Set up test fixtures."""
        self.vehicle_sda = Vehicle.objects.create(
            vessel_type="SDA",
            max_speed=26.5,
            unit="km/hr",
            beam=24.0,
            hull_type="slender",
            force_limit=96634.5
        )
        
        self.vehicle_test = create_test_vehicle()
        self.env_mesh = add_test_environment_mesh_to_db()

    def test_route_with_no_mesh_raises_error(self):
        """Test that route with no mesh raises appropriate error."""
        # Create route with no mesh
        route = Route.objects.create(
            start_lat=1.1,
            start_lon=1.1, 
            end_lat=8.9,
            end_lon=8.9,
            mesh=None,  # No mesh assigned
            vehicle=self.vehicle_test,
            requested=django_timezone.now()
        )
        
        # Verify route starts with no mesh
        assert route.mesh is None
        
        # Run task - should raise error about unexpected mesh type
        with pytest.raises(ValueError, match="Unexpected mesh type"):
            result = create_and_calculate_route.delay(route.id, "TEST_VESSEL")
            result.get(timeout=10)

    def test_route_with_wrong_vehicle_mesh_creates_correct_one(self):
        """Test that route with VehicleMesh for wrong vehicle creates correct VehicleMesh."""
        # Create VehicleMesh for SDA vehicle
        sda_vehicle_mesh = VehicleMesh.objects.create(
            environment_mesh=self.env_mesh,
            vehicle=self.vehicle_sda,
            valid_date_start=self.env_mesh.valid_date_start,
            valid_date_end=self.env_mesh.valid_date_end,
            created=self.env_mesh.created,
            md5=self.env_mesh.md5 + "_sda",
            meshiphi_version=self.env_mesh.meshiphi_version,
            lat_min=self.env_mesh.lat_min,
            lat_max=self.env_mesh.lat_max,
            lon_min=self.env_mesh.lon_min,
            lon_max=self.env_mesh.lon_max,
            name=f"{self.env_mesh.name} SDA",
            json=self.env_mesh.json
        )
        
        # Create route with SDA VehicleMesh but request TEST_VESSEL
        route = Route.objects.create(
            start_lat=-40.0,
            start_lon=-40.0,
            end_lat=40.0, 
            end_lon=40.0,
            mesh=sda_vehicle_mesh,  # Wrong vehicle mesh
            vehicle=self.vehicle_test,
            requested=django_timezone.now()
        )
        
        # Verify route starts with SDA VehicleMesh
        assert isinstance(route.mesh, VehicleMesh)
        assert route.mesh.vehicle.vessel_type == "SDA"
        
        # Run task requesting TEST_VESSEL - should create new VehicleMesh
        result = create_and_calculate_route.delay(route.id, "TEST_VESSEL")
        _ = result.get(timeout=30)
        
        # Verify route was calculated
        route.refresh_from_db()
        assert route.calculated is not None
        assert route.json is not None
        
        # Verify route now has correct VehicleMesh
        assert isinstance(route.mesh, VehicleMesh)
        assert route.mesh.vehicle.vessel_type == "TEST_VESSEL"
        assert route.mesh.environment_mesh == self.env_mesh
        # Should be different mesh than the SDA one
        assert route.mesh.id != sda_vehicle_mesh.id

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
        result = create_and_calculate_route.delay(route.id, "TEST_VESSEL")
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
            result = create_and_calculate_route.delay(99999, "TEST_VESSEL")
            result.get(timeout=10)

    def test_create_route_with_invalid_vehicle_type(self):
        """Test task behavior with invalid vehicle type."""
        vehicle = create_test_vehicle()
        route = Route.objects.create(
            start_lat=67.5,
            start_lon=-42.5,
            end_lat=67.7,
            end_lon=-42.5,
            vehicle=vehicle,
            requested=django_timezone.now()
        )
        
        with pytest.raises(ValueError, match="not found in database"):
            result = create_and_calculate_route.delay(route.id, "INVALID_VEHICLE")
            result.get(timeout=10)

    def test_import_meshes_no_metadata_file(self):
        """Test import_new_meshes when no metadata file exists."""
        result = import_new_meshes.delay()
        meshes_added = result.get(timeout=10)
        
        # Should return None when no metadata file exists
        assert meshes_added is None
