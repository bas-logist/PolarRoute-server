from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("route_api", "0019_mesh_protect_route_protect")]
AFTER = [("route_api", "0020_environment_vehicle_meshes")]


def mesh_fields(**kwargs):
    return dict(
        md5=kwargs.pop("md5"),
        valid_date_start="2024-08-04",
        valid_date_end="2024-08-06",
        created="2024-10-16T15:46:03Z",
        lat_min=-80.0,
        lat_max=-40.0,
        lon_min=-110.0,
        lon_max=-5.0,
        **kwargs,
    )


def vessel_mesh_json(vessel_info):
    return {"config": {"mesh_info": {"region": {}}, "vessel_info": vessel_info}}


class TestEnvironmentVehicleMeshMigration(TransactionTestCase):
    """Meshes before the split into environment and vehicle meshes are all vessel meshes."""

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        apps = executor.loader.project_state(BEFORE).apps
        Mesh = apps.get_model("route_api", "Mesh")
        Route = apps.get_model("route_api", "Route")
        Vehicle = apps.get_model("route_api", "Vehicle")

        Vehicle.objects.create(vessel_type="SDA", max_speed=99.0, unit="km/hr")

        # ids with gaps, as left behind by mesh cleanup
        Mesh.objects.create(
            id=5,
            **mesh_fields(
                md5="a",
                json=vessel_mesh_json({"vessel_type": "SDA", "max_speed": 30, "unit": "km/hr"}),
            ),
        )
        Mesh.objects.create(
            id=1,
            **mesh_fields(
                md5="b",
                json=vessel_mesh_json(
                    {
                        "vessel_type": "Slocum",
                        "max_speed": 1.25,
                        "unit": "km/hr",
                        "max_ice_conc": 10,
                    }
                ),
            ),
        )
        Mesh.objects.create(id=7, **mesh_fields(md5="c", json={"config": {}}))

        for mesh_id in (5, 1, 7):
            Route.objects.create(
                id=mesh_id, start_lat=0, start_lon=0, end_lat=1, end_lon=1, mesh_id=mesh_id
            )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)
        self.apps = executor.loader.project_state(AFTER).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_vessel_meshes_become_vehicle_meshes_with_same_ids(self):
        VehicleMesh = self.apps.get_model("route_api", "VehicleMesh")

        assert {m.pk: m.vehicle_id for m in VehicleMesh.objects.all()} == {
            5: "SDA",
            1: "Slocum",
        }
        assert all(m.environment_mesh_id is None for m in VehicleMesh.objects.all())

    def test_vehicle_is_created_from_vessel_info_or_reused(self):
        Vehicle = self.apps.get_model("route_api", "Vehicle")

        assert Vehicle.objects.get(vessel_type="SDA").max_speed == 99.0
        slocum = Vehicle.objects.get(vessel_type="Slocum")
        assert slocum.max_speed == 1.25
        assert slocum.max_ice_conc == 10
        assert slocum.created_by == "migration"

    def test_routes_keep_their_mesh_and_get_the_vehicle_and_vehicle_mesh(self):
        Route = self.apps.get_model("route_api", "Route")

        assert {r.pk: (r.mesh_id, r.vehicle_id, r.vehicle_mesh_id) for r in Route.objects.all()} == {
            5: (5, "SDA", 5),
            1: (1, "Slocum", 1),
            7: (7, None, None),
        }

    def test_mesh_without_vessel_info_is_unchanged(self):
        Mesh = self.apps.get_model("route_api", "Mesh")
        VehicleMesh = self.apps.get_model("route_api", "VehicleMesh")
        EnvironmentMesh = self.apps.get_model("route_api", "EnvironmentMesh")

        assert Mesh.objects.count() == 3
        assert not VehicleMesh.objects.filter(pk=7).exists()
        assert not EnvironmentMesh.objects.exists()
