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
from django.test import TestCase, TransactionTestCase, override_settings
import pytest
import s3fs
import yaml

from polarrouteserver.celery import app
from polarrouteserver.route_api.models import Mesh, Route
from polarrouteserver.route_api.tasks import import_new_meshes, optimise_route, cleanup_routes, cleanup_meshes, _get_s3_filesystem
from polarrouteserver.route_api.utils import calculate_md5
from .utils import add_test_mesh_to_db

class TestOptimiseRoute(TestCase):
    def setUp(self):
        self.start_point_name = "start point"
        self.end_point_name = "end point"
        self.mesh = add_test_mesh_to_db()
        self.route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh,
            start_name=self.start_point_name,
            end_name=self.end_point_name,
        )

    def test_optimise_route(self):
        """optimise_route should return a dictionary"""
        route_json = optimise_route(self.route.id)
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
            mesh=self.mesh
        )

        with pytest.raises(Ignore):
            optimise_route(self.out_of_mesh_route.id)

    def test_stale_mesh_warning(self):
        # make the created date on the mesh older than today for this test
        self.mesh.created = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=1)
        self.mesh.save()
        _ = optimise_route(self.route.id)
        route = Route.objects.get(id=self.route.id)
        assert "Latest available mesh from" in route.info["info"]

class TestTaskStatus(TransactionTestCase):

    def setUp(self):
        self.mesh = add_test_mesh_to_db()
        self.route = Route.objects.create(
            start_lat=1.1, start_lon=1.1, end_lat=8.9, end_lon=8.9, mesh=self.mesh
        )

    def test_task_status(self):
        """Test that task object status is updated appropriately."""

        task = optimise_route.delay(self.route.id)
        assert task.state == "SUCCESS"

    def test_unsmoothed_route_creation(self):
        """Test that route calculation task created unsmoothed route as well as the main route."""

        _ = optimise_route.delay(self.route.id)

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
            mesh=self.mesh
        )

        with pytest.raises(AssertionError):
            task = optimise_route.delay(self.out_of_mesh_route.id)
            assert task.state == "FAILURE"

@pytest.mark.usefixtures("tmp_path")
class ImportNewMeshesCommon(TestCase):

    @pytest.fixture(autouse=True)
    def _capture_tmp_path(self, tmp_path: Path):
        self.tmp_path = tmp_path

    def setUp(self):

        self.metadata_filename = "upload_metadata_test.yaml"
        self.metadata_filepath = Path(settings.MESH_DIR, self.metadata_filename)

        self.mesh_filenames = ["southern_test_mesh.vessel_20240807T091201.json",
                                "central_test_mesh.vessel.json"]
        
        self.dummy_mesh_json = [{
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
            # write out non zipped file just for calclating md5
            with open(Path(self.tmp_path, filename), 'w') as f:
                json.dump(self.dummy_mesh_json[i], f, indent=4)

        # create minimal test metadata
        self.metadata = {
            "records": [
                {   
                    "filepath": str(Path(self.tmp_path, self.mesh_filenames[0])),
                    "created": "20241016T154603",
                    "size": 123456,
                    "md5": calculate_md5(str(Path(self.tmp_path, self.mesh_filenames[0]))),
                    "meshiphi": "2.1.13",
                    "latlong": {
                        "latmin": -80.0,
                        "latmax": -40.0,
                        "lonmin":-110.0,
                        "lonmax":  -5.0,
                    }
                },
                {   
                    "filepath": str(Path(self.tmp_path, self.mesh_filenames[1])),
                    "created": "20241016T155252",
                    "size": 123456,
                    "md5": calculate_md5(str(Path(self.tmp_path, self.mesh_filenames[1]))),
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

    
    def test_import_new_meshes(self):
        
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            meshes_added = import_new_meshes()

        assert len(meshes_added) ==  len(self.mesh_filenames)

        for mesh in meshes_added:
            mesh_obj = Mesh.objects.get(id=mesh["id"])
            assert mesh_obj.id  == mesh["id"]
            assert mesh_obj.md5 == mesh["md5"]

        all_meshes = Mesh.objects.all()

        # run same meshes again and test not added again
        meshes_added = import_new_meshes()
        assert len(meshes_added) == 0

        all_meshes2 = Mesh.objects.all()
        assert list(all_meshes) == list(all_meshes2)

    # disable running tests for this method in this class, it's meant to be inherited by the TestImportNewMeshes classes so they both run the same test
    # parameterization would be better but it's complicated in this case
    test_import_new_meshes.__test__ = False

class TestImportNewMeshes(ImportNewMeshesCommon):

    def setUp(self):
        super().setUp()
       
        for i, filename in enumerate(self.mesh_filenames):
            # write out gzipped file
            with gzip.open(Path(settings.MESH_DIR, filename+".gz"), 'wb') as f:
                f.write(json.dumps(self.dummy_mesh_json[i]).encode('utf-8'))

        with open(self.metadata_filepath, 'w') as f:
            yaml.dump(self.metadata, f)

        with open(self.metadata_filepath, 'rb') as f_in:
            with gzip.open(Path(settings.MESH_DIR, self.metadata_filename+".gz"), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

    def tearDown(self):

        # cleanup files created for testing
        for filename in self.mesh_filenames + [self.metadata_filename]:
            os.remove(Path(settings.MESH_DIR, filename+".gz"))
    

@pytest.mark.usefixtures("s3_mock")
@override_settings(MESH_DIR="s3://mock-s3-bucket", MESH_METADATA_DIR="s3://mock-s3-bucket")
class TestImportNewMeshesFromS3(ImportNewMeshesCommon):

    def setUp(self):
        super().setUp()

        self.fs = _get_s3_filesystem()

        # Clear cached filesystem instances to avoid state leak
        s3fs.S3FileSystem.clear_instance_cache()

        # Set up test bucket and files inside mock S3
        self.fs.mkdir(settings.MESH_DIR[5:] if settings.MESH_DIR.startswith("s3://") else settings.MESH_DIR,
                          CreateBucketConfiguration={'LocationConstraint': settings.S3_REGION})

        for i, filename in enumerate(self.mesh_filenames):
            # write out gzipped file
            self._write_gz(f"{settings.MESH_DIR}/{filename}.gz", json.dumps(self.dummy_mesh_json[i]).encode('utf-8'))

        self._write(f"{settings.MESH_METADATA_DIR}/{self.metadata_filename}", yaml.safe_dump(self.metadata, sort_keys=False, indent=4))
        self._write_gz(f"{settings.MESH_METADATA_DIR}/{self.metadata_filename}.gz", yaml.safe_dump(self.metadata, sort_keys=False, indent=4).encode('utf-8'))

        

    def _write(self, path: str, content: str):
        """Helper method to write files to S3."""
        with self.fs.open(path, "w") as f:
            f.write(content)

    def _write_gz(self, path: str, content: str):
        """Helper method to write gzipped files to S3."""
        with self.fs.open(path, "wb") as f:
            with gzip.open(f, "wb") as gz:
                gz.write(content)


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
        self.mesh = add_test_mesh_to_db()
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
        self.new_mesh = add_test_mesh_to_db()
        self.old_mesh = add_test_mesh_to_db()
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
        self.old_mesh = add_test_mesh_to_db()
        self.old_mesh.created = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=7)
        self.old_mesh.protect = True
        self.old_mesh.save()
        assert len(Mesh.objects.all()) == 2
        cleanup_meshes()
        assert len(Mesh.objects.all()) == 2
