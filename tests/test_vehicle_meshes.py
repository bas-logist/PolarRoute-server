import copy
import hashlib
import json
import os

import pytest

from polarrouteserver.route_api.models import (
    EnvironmentMesh,
    Mesh,
    Vehicle,
    VehicleMesh,
)
from polarrouteserver.route_api.utils import (
    add_vehicle_to_environment_mesh,
    get_energy_source,
    get_vehicle_mesh,
    ingest_mesh,
)

from .utils import add_test_environment_mesh_to_db

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_vessel_mesh.json")

SDA = dict(
    vessel_type="SDA",
    max_speed=30,
    unit="km/hr",
    beam=10,
    hull_type="slender",
    force_limit=100000,
    max_ice_conc=80,
    min_depth=10,
)


@pytest.fixture
def vessel_mesh_json():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


@pytest.fixture
def environment_mesh_json(vessel_mesh_json):
    del vessel_mesh_json["config"]["vessel_info"]
    for cellbox in vessel_mesh_json["cellboxes"]:
        for key in ("speed", "resistance", "fuel"):
            cellbox.pop(key, None)
    return vessel_mesh_json


@pytest.fixture
def sda():
    return Vehicle.objects.create(**SDA)


@pytest.mark.django_db
class TestAddVehicleToEnvironmentMesh:
    def test_builds_vehicle_mesh(self, sda):
        env_mesh = add_test_environment_mesh_to_db()

        vehicle_mesh = add_vehicle_to_environment_mesh(env_mesh, sda)

        assert vehicle_mesh.environment_mesh_id == env_mesh.id
        assert vehicle_mesh.vehicle_id == "SDA"
        assert vehicle_mesh.created == env_mesh.created
        assert vehicle_mesh.valid_date_start == env_mesh.valid_date_start
        assert (vehicle_mesh.lat_min, vehicle_mesh.lon_max) == (
            env_mesh.lat_min,
            env_mesh.lon_max,
        )
        assert get_energy_source(vehicle_mesh.json) == "fuel"
        assert vehicle_mesh.json["config"]["vessel_info"]["vessel_type"] == "SDA"

    def test_existing_vehicle_mesh_is_reused(self, sda):
        env_mesh = add_test_environment_mesh_to_db()

        first = add_vehicle_to_environment_mesh(env_mesh, sda)
        second = add_vehicle_to_environment_mesh(env_mesh, sda)

        assert first.id == second.id
        assert VehicleMesh.objects.count() == 1

    def test_missing_ice_data_is_stored_as_missing_and_the_build_succeeds(self, sda):
        """Missing data (None) is not replaced with a value in the mesh. PolarRoute treats it as ice-free."""
        env_mesh = add_test_environment_mesh_to_db()
        for cellbox in env_mesh.json["cellboxes"]:
            cellbox["SIC"] = None
        env_mesh.save()

        vehicle_mesh = add_vehicle_to_environment_mesh(env_mesh, sda)

        assert get_energy_source(vehicle_mesh.json) == "fuel"
        assert env_mesh.json["cellboxes"][0]["SIC"] is None
        assert vehicle_mesh.json["cellboxes"][0]["SIC"] is None
        # the same speed as with no ice at all
        assert vehicle_mesh.json["cellboxes"][0]["speed"][0] == SDA["max_speed"]

    def test_unknown_vessel_type_is_rejected(self):
        env_mesh = add_test_environment_mesh_to_db()
        unknown = Vehicle.objects.create(
            vessel_type="NOT_A_KNOWN_VESSEL", max_speed=10.0, unit="km/hr"
        )

        with pytest.raises(RuntimeError, match="not in known list of vessels"):
            add_vehicle_to_environment_mesh(env_mesh, unknown)

        assert not VehicleMesh.objects.exists()


@pytest.mark.django_db
class TestGetVehicleMesh:
    def test_environment_mesh_builds_vehicle_mesh(self, sda):
        env_mesh = add_test_environment_mesh_to_db()

        # the id of a Mesh object is also the id of its EnvironmentMesh
        vehicle_mesh = get_vehicle_mesh(Mesh.objects.get(id=env_mesh.id), sda)

        assert isinstance(vehicle_mesh, VehicleMesh)
        assert vehicle_mesh.environment_mesh_id == env_mesh.id

    def test_vehicle_mesh_for_same_vehicle_is_used_as_it_is(self, sda):
        env_mesh = add_test_environment_mesh_to_db()
        vehicle_mesh = add_vehicle_to_environment_mesh(env_mesh, sda)

        assert get_vehicle_mesh(Mesh.objects.get(id=vehicle_mesh.id), sda).id == vehicle_mesh.id

    def test_vehicle_mesh_for_other_vehicle_builds_from_its_environment_mesh(self, sda):
        env_mesh = add_test_environment_mesh_to_db()
        sda_mesh = add_vehicle_to_environment_mesh(env_mesh, sda)
        boaty = Vehicle.objects.create(
            vessel_type="BoatyMcBoatFace",
            max_speed=3.6,
            unit="km/hr",
            max_ice_conc=10,
            min_depth=10,
        )

        boaty_mesh = get_vehicle_mesh(Mesh.objects.get(id=sda_mesh.id), boaty)

        assert boaty_mesh.id != sda_mesh.id
        assert boaty_mesh.environment_mesh_id == env_mesh.id
        assert boaty_mesh.vehicle_id == "BoatyMcBoatFace"
        assert get_energy_source(boaty_mesh.json) == "battery"
        assert get_energy_source(sda_mesh.json) == "fuel"

    def test_imported_vehicle_mesh_for_other_vehicle_cannot_be_used(self, sda):
        other = Vehicle.objects.create(vessel_type="OTHER", max_speed=1.0, unit="km/hr")
        env_mesh = add_test_environment_mesh_to_db()
        imported = VehicleMesh.objects.create(
            name="imported",
            md5="imported",
            vehicle=other,
            valid_date_start=env_mesh.valid_date_start,
            valid_date_end=env_mesh.valid_date_end,
            created=env_mesh.created,
            lat_min=-1, lat_max=1, lon_min=-1, lon_max=1,
        )

        with pytest.raises(ValueError, match="no environment mesh"):
            get_vehicle_mesh(Mesh.objects.get(id=imported.id), sda)

    def test_mesh_of_unknown_type_cannot_be_used(self, sda):
        env_mesh = add_test_environment_mesh_to_db()
        plain = Mesh.objects.create(
            name="plain",
            md5="plain",
            valid_date_start=env_mesh.valid_date_start,
            valid_date_end=env_mesh.valid_date_end,
            created=env_mesh.created,
            lat_min=-1, lat_max=1, lon_min=-1, lon_max=1,
        )

        with pytest.raises(ValueError, match="not an environment or vehicle mesh"):
            get_vehicle_mesh(plain, sda)


class TestGetEnergySource:
    def test_fuel(self):
        assert get_energy_source({"cellboxes": [{"id": "0"}, {"fuel": [1.0]}]}) == "fuel"

    def test_battery(self):
        assert get_energy_source({"cellboxes": [{"battery": [1.0]}]}) == "battery"

    def test_neither(self):
        with pytest.raises(ValueError, match="fuel or battery"):
            get_energy_source({"cellboxes": [{"id": "0"}]})


@pytest.mark.django_db
class TestIngestMesh:
    def test_environment_mesh(self, environment_mesh_json):
        mesh, created, mesh_type = ingest_mesh(environment_mesh_json, "env.json")

        assert created
        assert mesh_type == "EnvironmentMesh"
        assert isinstance(mesh, EnvironmentMesh)
        assert mesh.meshiphi_version == "manually_inserted"
        assert not Vehicle.objects.exists()

    def test_vehicle_mesh_creates_vehicle(self, vessel_mesh_json):
        mesh, created, mesh_type = ingest_mesh(vessel_mesh_json, "vessel.json")

        assert created
        assert mesh_type == "VehicleMesh"
        assert isinstance(mesh, VehicleMesh)
        assert mesh.environment_mesh is None
        assert mesh.vehicle.vessel_type == "SDA"
        assert mesh.vehicle.max_speed == 30
        assert mesh.vehicle.beam == 10

    def test_existing_vehicle_is_not_changed(self, vessel_mesh_json):
        Vehicle.objects.create(vessel_type="SDA", max_speed=99.0, unit="km/hr")

        mesh, _, _ = ingest_mesh(vessel_mesh_json, "vessel.json")

        assert mesh.vehicle.max_speed == 99.0

    def test_same_mesh_not_added_twice(self, environment_mesh_json):
        first, created, _ = ingest_mesh(copy.deepcopy(environment_mesh_json), "env.json")
        second, created_again, _ = ingest_mesh(copy.deepcopy(environment_mesh_json), "env.json")

        assert created and not created_again
        assert first.id == second.id
        assert Mesh.objects.count() == 1

    def test_expected_md5(self, environment_mesh_json):
        md5 = hashlib.md5(json.dumps(environment_mesh_json, indent=4).encode()).hexdigest()

        mesh, _, _ = ingest_mesh(environment_mesh_json, "env.json", expected_md5=md5)
        assert mesh.md5 == md5

        with pytest.raises(ValueError, match="does not match"):
            ingest_mesh(environment_mesh_json, "env.json", expected_md5="wrong")

    def test_vessel_info_without_vessel_type(self, vessel_mesh_json):
        del vessel_mesh_json["config"]["vessel_info"]["vessel_type"]

        with pytest.raises(ValueError, match="no vessel_type"):
            ingest_mesh(vessel_mesh_json, "vessel.json")

    def test_new_vehicle_needs_speed_and_unit(self, vessel_mesh_json):
        del vessel_mesh_json["config"]["vessel_info"]["unit"]

        with pytest.raises(ValueError, match="missing required fields"):
            ingest_mesh(vessel_mesh_json, "vessel.json")

    def test_not_a_mesh(self):
        with pytest.raises(ValueError, match="not a mesh"):
            ingest_mesh({"some": "other json"}, "other.json")
