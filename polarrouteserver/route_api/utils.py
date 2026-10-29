import copy
import hashlib
import json
import logging
import math
from datetime import UTC, datetime
from typing import Any

import haversine
import numpy as np
import pandas as pd
import polar_route
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from polar_route.route_calc import route_calc
from polar_route.route_planner.route_planner import RoutePlanner
from polar_route.utils import convert_decimal_days, extract_geojson_routes
from polar_route.vessel_performance.vessel_performance_modeller import (
    VesselPerformanceModeller,
)

from .models import EnvironmentMesh, Mesh, Route, Vehicle, VehicleMesh

logger = logging.getLogger(__name__)

VEHICLE_OPTIONAL_FIELDS = (
    "max_ice_conc",
    "min_depth",
    "max_wave",
    "excluded_zones",
    "neighbour_splitting",
    "beam",
    "hull_type",
    "force_limit",
)


class NotAMeshError(ValueError):
    """The json is not a mesh."""


def select_mesh(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    vehicle_type: str | None = None,
) -> list[Mesh] | None:
    """Find the most suitable meshes from the database for a given set of start and end coordinates.

    Candidates are all EnvironmentMeshes, plus (if vehicle_type is given) imported
    VehicleMeshes of that vehicle which have no EnvironmentMesh to be built from.
    VehicleMeshes built from an EnvironmentMesh are not candidates themselves: they are
    found or built from the EnvironmentMesh when the route is calculated.

    Returns a list of Mesh objects, ordered smallest first from the most recent creation
    date, or None if there are none.
    """

    usable = Q(environmentmesh__isnull=False)
    if vehicle_type:
        usable |= Q(
            vehiclemesh__vehicle_id=vehicle_type,
            vehiclemesh__environment_mesh__isnull=True,
        )

    # get meshes which contain both start and end points
    containing_meshes = (
        Mesh.objects.filter(usable)
        .filter(
            lat_min__lte=start_lat,
            lat_max__gte=start_lat,
            lon_min__lte=start_lon,
            lon_max__gte=start_lon,
        )
        .filter(
            lat_min__lte=end_lat,
            lat_max__gte=end_lat,
            lon_min__lte=end_lon,
            lon_max__gte=end_lon,
        )
    )

    latest = containing_meshes.order_by("-created").first()
    if latest is None:
        return None

    # get all valid meshes from the most recent creation date, smallest first. Where meshes
    # are the same size, imported vehicle meshes come first, as they don't need to be built.
    valid_meshes = list(containing_meshes.filter(created__date=latest.created.date()))
    vehicle_mesh_ids = set(
        VehicleMesh.objects.filter(pk__in=[m.pk for m in valid_meshes]).values_list(
            "pk", flat=True
        )
    )
    return sorted(
        valid_meshes, key=lambda mesh: (mesh.size, mesh.pk not in vehicle_mesh_ids)
    )


def route_exists(
    meshes: Mesh | list[Mesh],
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    vehicle: Vehicle,
) -> Route | None:
    """Check if a route of given parameters has already been calculated for the vehicle.
    Works through list of meshes in order, returns first matching route
    Return None if not and the route object if it has.
    """

    if isinstance(meshes, Mesh):
        meshes = [meshes]

    for mesh in meshes:
        same_mesh_routes = Route.objects.filter(mesh=mesh, vehicle=vehicle)

        # use set to preserve uniqueness
        successful_route_ids = set()
        # remove any failed routes
        for route in same_mesh_routes:
            # job_set can't be filtered since status is a property method
            for job in route.job_set.all():
                # Use the model's status property
                if job.status != "FAILURE":
                    successful_route_ids.add(route.id)

        successful_routes = same_mesh_routes.filter(id__in=successful_route_ids)

        # if there are none return None
        if len(successful_routes) == 0:
            continue
        else:
            exact_routes = successful_routes.filter(
                start_lat=start_lat,
                start_lon=start_lon,
                end_lat=end_lat,
                end_lon=end_lon,
            )

            if len(exact_routes) == 1:
                return exact_routes[0]
            elif len(exact_routes) > 1:
                # TODO if multiple matching routes exist, which to return?
                return exact_routes[0]
            else:
                # if no exact routes, look for any that are close enough
                return _closest_route_in_tolerance(
                    same_mesh_routes, start_lat, start_lon, end_lat, end_lon
                )
    return None


def _closest_route_in_tolerance(
    routes: list,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    tolerance_nm: float = settings.WAYPOINT_DISTANCE_TOLERANCE,
) -> Route | None:
    """Takes a list of routes and returns the closest if any are within tolerance, or None."""

    def point_within_tolerance(point_1: tuple, point_2: tuple) -> bool:
        return haversine_distance(point_1, point_2) < tolerance_nm

    def haversine_distance(point_1: tuple, point_2: tuple) -> float:
        return haversine.haversine(point_1, point_2, unit=haversine.Unit.NAUTICAL_MILES)

    routes_in_tolerance = []
    for route in routes:
        if point_within_tolerance(
            (start_lat, start_lon), (route.start_lat, route.start_lon)
        ) and point_within_tolerance(
            (end_lat, end_lon), (route.end_lat, route.end_lon)
        ):
            routes_in_tolerance.append(
                {
                    "id": route.id,
                }
            )

    if len(routes_in_tolerance) == 0:
        return None
    elif len(routes_in_tolerance) == 1:
        return Route.objects.get(id=routes_in_tolerance[0]["id"])
    else:
        for i, route_dict in enumerate(routes_in_tolerance):
            route = Route.objects.get(id=route_dict["id"])
            route_dict.update(
                {
                    "cumulative_distance": haversine_distance(
                        (start_lat, start_lon), (route.start_lat, route.start_lon)
                    )
                    + haversine_distance(
                        (end_lat, end_lon), (route.end_lat, route.end_lon)
                    )
                }
            )

        from operator import itemgetter

        closest_route = min(routes_in_tolerance, key=itemgetter("cumulative_distance"))
        return Route.objects.get(id=closest_route["id"])


def evaluate_route(route_json: dict, mesh: VehicleMesh) -> dict:
    """Run route_calc method from PolarRoute to evaluate the fuel usage and travel time of a route.

    Args:
        route_json (dict): route to evaluate in geojson format.
        mesh (VehicleMesh): mesh including vehicle performance on which to evaluate the route.

    Returns:
        dict: evaluated route
    """

    properties = route_json["features"][0].get("properties")
    if properties is None:
        properties = route_json["features"][0]["properties"] = {}
    properties.setdefault("from", "Start")
    properties.setdefault("to", "End")

    try:
        calc_route = route_calc(route_json, mesh=mesh.json, route_type="smoothed")
        time_days = calc_route["features"][0]["properties"]["traveltime"][-1]
        time_str = convert_decimal_days(time_days)
        fuel = round(calc_route["features"][0]["properties"]["fuel"][-1], 2)

    except Exception:  # noqa BLE001
        logger.exception("Error in evaluate_route")
        return None

    return {
        "route": calc_route,
        "time_days": time_days,
        "time_str": time_str,
        "fuel_tonnes": fuel,
    }


def select_mesh_for_route_evaluation(
    route: dict, vehicle_type: str | None = None
) -> list[Mesh] | None:
    """Select meshes from the database to be used for route evaluation.
    The latest meshes containing all points in the route will be chosen.
    If no suitable meshes are available, return None.

    Args:
        route (dict): GeoJSON route to be evaluated.
        vehicle_type (str, optional): vehicle the route is evaluated for.

    Returns:
        list[Mesh] | None: Selected mesh objects or None.
    """

    # GeoJSON coordinates are [longitude, latitude]
    coordinates = route["features"][0]["geometry"]["coordinates"]
    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]

    return select_mesh(min(lats), min(lons), max(lats), max(lons), vehicle_type)


def check_mesh_data(mesh: Mesh) -> str:
    """Check a mesh object for missing data sources.

    Args:
        mesh (Mesh): mesh object to evaluate.

    Returns:
        A user-friendly warning message as a string.
    """

    message = ""

    mesh_data_sources = mesh.json["config"]["mesh_info"].get("data_sources", None)

    # check for completely absent data sources
    if mesh_data_sources is None:
        message = "Mesh has no data sources."
        return message

    expected_sources = settings.EXPECTED_MESH_DATA_SOURCES
    expected_num_data_files = settings.EXPECTED_MESH_DATA_FILES

    for data_type, data_loader in expected_sources.items():
        # check for missing individual data sources
        data_source = [d for d in mesh_data_sources if d["loader"] == data_loader]
        if len(data_source) == 0:
            message += f"Warning: This mesh is missing data on the following parameters: {data_type}.\n"

            # skip to the next data source
            continue

        # check for unexpected number of data files
        data_source_num_expected_files = expected_num_data_files.get(data_loader, None)
        if data_source_num_expected_files is not None:
            actual_num_files = len(
                [f for f in data_source[0]["params"]["files"] if f != ""]
            )  # number of files removing empty strings
            if actual_num_files != data_source_num_expected_files:
                message += f"Warning: {actual_num_files} of expected {data_source_num_expected_files} days' data available for {data_type}.\n"

    return message


def check_missing_ice_data(mesh: Mesh) -> str:
    """Check a mesh object for sea cells without sea ice concentration (SIC) data.

    PolarRoute treats a missing SIC as ice-free when modelling vehicle performance, so
    routes through these cells are not slowed or avoided because of ice.

    Args:
        mesh (Mesh): mesh object to evaluate.

    Returns:
        A user-friendly warning message as a string, empty if no data is missing.
    """

    sea_cells = [c for c in mesh.json.get("cellboxes", []) if not c.get("land")]
    missing = sum(
        1
        for c in sea_cells
        if c.get("SIC") is None
        or (isinstance(c["SIC"], float) and math.isnan(c["SIC"]))
    )
    if missing == 0:
        return ""

    return (
        f"Warning: {missing} of {len(sea_cells)} sea cells have no sea ice concentration data, "
        "these are treated as ice-free.\n"
    )


def _get_or_create_vehicle(vessel_info: dict) -> Vehicle:
    """Find the Vehicle for the vessel_info of a mesh, creating it if it doesn't exist."""

    vessel_type = vessel_info.get("vessel_type")
    if not vessel_type:
        raise ValueError("Vehicle mesh found but no vessel_type specified in config")

    vehicle = Vehicle.objects.filter(vessel_type=vessel_type).first()
    if vehicle is not None:
        return vehicle

    max_speed = vessel_info.get("max_speed")
    unit = vessel_info.get("unit")
    if max_speed is None or not unit:
        raise ValueError(
            f"Vehicle mesh missing required fields: max_speed={max_speed}, unit={unit}"
        )

    logger.info(f"Vehicle type '{vessel_type}' not found in database, creating it")
    return Vehicle.objects.create(
        vessel_type=vessel_type,
        max_speed=max_speed,
        unit=unit,
        created=timezone.now(),
        created_by="mesh ingestion",
        **{f: vessel_info[f] for f in VEHICLE_OPTIONAL_FIELDS if f in vessel_info},
    )


def ingest_mesh(
    mesh_json: dict[str, Any],
    mesh_filename: str,
    metadata_record: dict[str, Any] | None = None,
    expected_md5: str | None = None,
) -> tuple[Mesh, bool, str]:
    """Ingest a mesh into the database.

    A mesh with `vessel_info` in its config is a VehicleMesh (its Vehicle is created if it
    doesn't exist), otherwise it is an EnvironmentMesh. Meshes are identified by the md5
    of their json, so a mesh already in the database is not added again.

    Args:
        mesh_json: The mesh JSON.
        mesh_filename: Name of the mesh file.
        metadata_record: Record from the mesh upload metadata. If not given the
            mesh is treated as manually inserted.
        expected_md5: If given, the md5 the mesh is required to have.

    Returns:
        The mesh object, whether it was newly created, and the mesh type
        ("EnvironmentMesh" or "VehicleMesh").

    Raises:
        ValueError: if the json is not a mesh, the md5 doesn't match or the vehicle
            information is incomplete.
    """

    try:
        config = mesh_json["config"]
        region = config["mesh_info"]["region"]
    except (KeyError, TypeError) as e:
        raise NotAMeshError(f"{mesh_filename} is not a mesh: missing {e}") from e

    md5 = hashlib.md5(json.dumps(mesh_json, indent=4).encode()).hexdigest()
    if expected_md5 and md5 != expected_md5:
        raise ValueError(f"Mesh MD5 {md5} does not match expected MD5 {expected_md5}")

    defaults = {
        "name": mesh_filename,
        "valid_date_start": datetime.strptime(region["start_time"], "%Y-%m-%d").replace(
            tzinfo=UTC
        ),
        "valid_date_end": datetime.strptime(region["end_time"], "%Y-%m-%d").replace(
            tzinfo=UTC
        ),
        "json": mesh_json,
    }
    if metadata_record:
        defaults |= {
            "created": datetime.strptime(
                metadata_record["created"], "%Y%m%dT%H%M%S"
            ).replace(tzinfo=UTC),
            "meshiphi_version": metadata_record["meshiphi"],
            "lat_min": metadata_record["latlong"]["latmin"],
            "lat_max": metadata_record["latlong"]["latmax"],
            "lon_min": metadata_record["latlong"]["lonmin"],
            "lon_max": metadata_record["latlong"]["lonmax"],
        }
    else:
        defaults |= {
            "created": timezone.now(),
            "meshiphi_version": "manually_inserted",
            "lat_min": region["lat_min"],
            "lat_max": region["lat_max"],
            "lon_min": region["long_min"],
            "lon_max": region["long_max"],
        }

    if "vessel_info" in config:
        defaults["vehicle"] = _get_or_create_vehicle(config["vessel_info"])
        mesh, created = VehicleMesh.objects.get_or_create(md5=md5, defaults=defaults)
        return mesh, created, "VehicleMesh"

    mesh, created = EnvironmentMesh.objects.get_or_create(md5=md5, defaults=defaults)
    return mesh, created, "EnvironmentMesh"


def get_energy_source(mesh_json: dict) -> str:
    """Return which energy use ("fuel" or "battery") the vehicle performance in a mesh models."""

    cellboxes = mesh_json["cellboxes"]
    for source in ("fuel", "battery"):
        if any(source in cellbox for cellbox in cellboxes):
            return source
    raise ValueError("Mesh has no vehicle performance data for fuel or battery use.")


def optimise_route(mesh_json: dict, route: Route) -> list:
    """Calculate optimal routes with PolarRoute from a mesh with vehicle performance.

    The route is optimised for travel time and for the energy use the vehicle in the mesh
    models (fuel or battery). The Route is updated in the database as results become available.

    Args:
        mesh_json: json of a VehicleMesh.
        route: Route database object with start/end coordinates and metadata.

    Returns:
        smoothed routes as list of geojson dictionaries
    """
    logger.info(f"Calculating route optimization for route {route.id}")

    energy_source = get_energy_source(mesh_json)
    logger.info(f"Optimising for {energy_source} use.")

    # convert waypoints into pandas dataframe for PolarRoute
    waypoints = pd.DataFrame(
        {
            "Name": [
                "Start" if route.start_name is None else route.start_name,
                "End" if route.end_name is None else route.end_name,
            ],
            "Lat": [route.start_lat, route.end_lat],
            "Long": [route.start_lon, route.end_lon],
            "Source": ["X", np.nan],
            "Destination": [np.nan, "X"],
        }
    )

    unsmoothed_routes = []
    route_planners = []

    energy_config = {"fuel": settings.FUEL_CONFIG, "battery": settings.BATTERY_CONFIG}[
        energy_source
    ]
    # path variables have to be the same for both optimisations, and match the vehicle
    traveltime_config = settings.TRAVELTIME_CONFIG | {
        "path_variables": energy_config["path_variables"]
    }

    for config in (traveltime_config, energy_config):
        rp = RoutePlanner(copy.deepcopy(mesh_json), config)

        # Calculate optimal dijkstra path between waypoints
        rp.compute_routes(waypoints)
        route_planners.append(rp)

        # save the initial unsmoothed route
        logger.info(
            f"Saving unsmoothed Dijkstra paths for {config['objective_function']}-optimised route."
        )
        if len(rp.routes_dijkstra) == 0:
            raise ValueError("Inaccessible. No routes found.")
        route_geojson = extract_geojson_routes(rp.to_json())
        route_geojson[0]["features"][0]["properties"]["objective_function"] = config[
            "objective_function"
        ]
        unsmoothed_routes.append(route_geojson)

    # Update route with unsmoothed data, it is only complete once smoothed
    route.json_unsmoothed = unsmoothed_routes
    route.polar_route_version = polar_route.__version__
    route.save()

    smoothed_routes = []
    for i, rp in enumerate(route_planners):
        # Smooth the dijkstra routes
        rp.compute_smoothed_routes()
        # Save the smoothed route(s)
        logger.info(f"Route smoothing {i + 1}/{len(route_planners)} complete.")
        route_geojson = extract_geojson_routes(rp.to_json())
        route_geojson[0]["features"][0]["properties"]["objective_function"] = rp.config[
            "objective_function"
        ]
        smoothed_routes.append(route_geojson)

    # Update the database
    route.json = smoothed_routes
    route.calculated = timezone.now()
    route.polar_route_version = polar_route.__version__
    route.save()

    return smoothed_routes


def add_vehicle_to_environment_mesh(
    environment_mesh: EnvironmentMesh, vehicle: Vehicle
) -> VehicleMesh:
    """Get the VehicleMesh for an EnvironmentMesh and Vehicle, building it if it doesn't exist.

    Building adds the performance of the vehicle to the environment mesh using PolarRoute's
    VesselPerformanceModeller. The VehicleMesh takes the validity, region and creation time
    of the EnvironmentMesh.

    Raises:
        RuntimeError: if the performance modelling fails, for example because
            PolarRoute has no performance model for the vessel_type.
    """

    existing = VehicleMesh.objects.filter(
        environment_mesh=environment_mesh, vehicle=vehicle
    ).first()
    if existing is not None:
        return existing

    logger.info(
        f"Adding vehicle {vehicle.vessel_type} to environment mesh {environment_mesh.id}"
    )

    vehicle_config = {
        "vessel_type": vehicle.vessel_type,
        "max_speed": vehicle.max_speed,
        "unit": vehicle.unit,
    }
    for field in VEHICLE_OPTIONAL_FIELDS:
        value = getattr(vehicle, field)
        if value is not None:
            vehicle_config[field] = value

    try:
        vp = VesselPerformanceModeller(
            env_mesh_json=copy.deepcopy(environment_mesh.json),
            vessel_config=vehicle_config,
        )
        vp.model_accessibility()
        vp.model_performance()
        vessel_mesh_json = vp.to_json()
    except Exception as e:  # noqa BLE001
        logger.error(f"Error during vessel performance modelling: {e}")
        raise RuntimeError(
            f"Failed to create vehicle mesh for {vehicle.vessel_type}: {e}"
        ) from e

    try:
        with transaction.atomic():
            vehicle_mesh = VehicleMesh.objects.create(
                environment_mesh=environment_mesh,
                vehicle=vehicle,
                meshiphi_version=environment_mesh.meshiphi_version,
                md5=hashlib.md5(
                    json.dumps(vessel_mesh_json, indent=4).encode()
                ).hexdigest(),
                valid_date_start=environment_mesh.valid_date_start,
                valid_date_end=environment_mesh.valid_date_end,
                created=environment_mesh.created,
                lat_min=environment_mesh.lat_min,
                lat_max=environment_mesh.lat_max,
                lon_min=environment_mesh.lon_min,
                lon_max=environment_mesh.lon_max,
                name=f"{environment_mesh.name}_vehicle_{vehicle.vessel_type}",
                json=vessel_mesh_json,
            )
    except IntegrityError:
        # another task built it at the same time
        return VehicleMesh.objects.get(
            environment_mesh=environment_mesh, vehicle=vehicle
        )

    logger.info(
        f"Created VehicleMesh {vehicle_mesh.id} for vehicle {vehicle.vessel_type}"
    )
    return vehicle_mesh


def get_vehicle_mesh(mesh: Mesh, vehicle: Vehicle) -> VehicleMesh:
    """Get the mesh with the performance of a vehicle to calculate a route on.

    Args:
        mesh: an EnvironmentMesh, or a VehicleMesh (which is used as it is if it is for the
            vehicle, otherwise the vehicle is added to the EnvironmentMesh it was built from).
        vehicle: the vehicle the route is for.

    Raises:
        ValueError: if no mesh can be found for the vehicle.
    """

    vehicle_mesh = VehicleMesh.objects.filter(pk=mesh.pk).first()
    if vehicle_mesh is not None:
        if vehicle_mesh.vehicle_id == vehicle.pk:
            return vehicle_mesh
        environment_mesh = vehicle_mesh.environment_mesh
        if environment_mesh is None:
            raise ValueError(
                f"Mesh {mesh.id} is for vehicle '{vehicle_mesh.vehicle_id}' and has no "
                f"environment mesh to add vehicle '{vehicle.pk}' to."
            )
    else:
        environment_mesh = EnvironmentMesh.objects.filter(pk=mesh.pk).first()
        if environment_mesh is None:
            raise ValueError(f"Mesh {mesh.id} is not an environment or vehicle mesh.")

    return add_vehicle_to_environment_mesh(environment_mesh, vehicle)
