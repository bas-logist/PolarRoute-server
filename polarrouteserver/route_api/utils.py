import hashlib
import json
import logging
import copy
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import Union, Tuple, Dict, Any

from django.conf import settings
from django.utils import timezone
import haversine
import numpy as np
import pandas as pd
import polar_route
from polar_route.route_planner.route_planner import RoutePlanner
from polar_route.utils import extract_geojson_routes
from polar_route.vessel_performance.vessel_performance_modeller import (
    VesselPerformanceModeller,
)
from polar_route.vessel_performance.vessels.example_ship import ExampleShip
from polar_route.route_calc import route_calc
from polar_route.utils import convert_decimal_days

from .models import Route, EnvironmentMesh, VehicleMesh, Vehicle

logger = logging.getLogger(__name__)


def select_mesh(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    vehicle_type: str = None,
) -> Union[list[Union[VehicleMesh, EnvironmentMesh]], None]:
    """Find the most suitable mesh from the database for a given set of start and end coordinates.
    If vehicle_type is specified, look for VehicleMesh objects for that vehicle_type.
    If no vehicle_type specified or specific vehicle type not found, fall back to EnvironmentMesh
    objects.

    Returns either a list of mesh objects (VehicleMesh for specific vehicle_type, EnvironmentMesh
    as fallback) or None.

    Args:
        start_lat, start_lon, end_lat, end_lon: Coordinate bounds
        vehicle_type: Optional vehicle type to prioritize in search

    Returns:
        List of mesh objects in priority order, or None if no suitable meshes found
    """

    def get_meshes_in_bounds(model_class):
        """Helper function to get meshes of a specific type within coordinate bounds"""
        return model_class.objects.filter(
            lat_min__lte=start_lat,
            lat_max__gte=start_lat,
            lon_min__lte=start_lon,
            lon_max__gte=start_lon,
        ).filter(
            lat_min__lte=end_lat,
            lat_max__gte=end_lat,
            lon_min__lte=end_lon,
            lon_max__gte=end_lon,
        )

    def filter_latest_and_smallest(meshes):
        """Helper function to filter by latest date and return smallest meshes"""
        if not meshes.exists():
            return []

        latest_date = meshes.latest("created").created.date()
        valid_meshes = meshes.filter(created__date=latest_date)
        return sorted(valid_meshes, key=lambda mesh: mesh.size)

    try:
        # VehicleMesh for specific vehicle type (if specified)
        if vehicle_type:
            try:
                vehicle = Vehicle.objects.get(vessel_type=vehicle_type)
                vehicle_meshes = get_meshes_in_bounds(VehicleMesh).filter(
                    vehicle=vehicle
                )
                result = filter_latest_and_smallest(vehicle_meshes)
                if result:
                    return result
            except Vehicle.DoesNotExist:
                pass

        # If no vehicle_type specified, or specific vehicle type not found
        environment_meshes = get_meshes_in_bounds(EnvironmentMesh)
        result = filter_latest_and_smallest(environment_meshes)
        if result:
            return result

        return None

    except (EnvironmentMesh.DoesNotExist, VehicleMesh.DoesNotExist):
        return None


def route_exists(
    meshes: Union[VehicleMesh, list[VehicleMesh]],
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> Union[Route, None]:
    """Check if a route of given parameters has already been calculated.
    Works through list of VehicleMesh objects in order, returns first matching route.
    Only applies to VehicleMesh objects. Return None if not and the route object if it has.

    Args:
        meshes: VehicleMesh object or list of VehicleMesh objects
    """

    if isinstance(meshes, VehicleMesh):
        meshes = [meshes]

    for mesh in meshes:
        same_mesh_routes = Route.objects.filter(mesh=mesh)

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
) -> Union[Route, None]:
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
            routes_in_tolerance[i].update(
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

        closest_route = sorted(
            routes_in_tolerance, key=itemgetter("cumulative_distance")
        )[0]
        return Route.objects.get(id=closest_route["id"])


def calculate_md5(filename):
    """create md5sum checksum for any file"""
    hash_md5 = hashlib.md5()

    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def evaluate_route(route_json: dict, mesh: VehicleMesh) -> dict:
    """Run calculate_route method from PolarRoute to evaluate the fuel usage and travel time of a route.

    Args:
        route_json (dict): route to evaluate in geojson format.
        mesh (VehicleMesh): VehicleMesh object on which to evaluate the route.

    Returns:
        dict: evaluated route
    """

    if route_json["features"][0].get("properties", None) is None:
        route_json["features"][0]["properties"] = {"from": "Start", "to": "End"}

    # Extract coordinates from GeoJSON
    coordinates = route_json["features"][0]["geometry"]["coordinates"]

    waypoints = []
    for i, coord in enumerate(coordinates):
        name = "Start" if i == 0 else ("End" if i == len(coordinates) - 1 else f"WP{i}")
        source = "X" if i == 0 else np.nan
        dest = "X" if i == len(coordinates) - 1 else np.nan

        waypoints.append(
            {
                "Name": name,
                "Lat": coord[1],
                "Long": coord[0],
                "Source": source,
                "Destination": dest,
                "order": i,
                "id": 0,  # Single route ID
            }
        )

    df = pd.DataFrame(waypoints)

    try:
        # Use route_calc API signature: (df, from_wp, to_wp, mesh, route_type)
        calc_route = route_calc(
            df=df, from_wp="Start", to_wp="End", mesh=mesh.json, route_type="smoothed"
        )
        time_days = calc_route["features"][0]["properties"]["traveltime"][-1]
        time_str = convert_decimal_days(time_days)
        fuel = round(calc_route["features"][0]["properties"]["fuel"][-1], 2)

    except Exception as e:
        logger.error(e)
        return None

    return dict(
        route=calc_route, time_days=time_days, time_str=time_str, fuel_tonnes=fuel
    )


def select_mesh_for_route_evaluation(
    route: dict, vehicle_type: str = None
) -> Union[list[VehicleMesh], None]:
    """Select VehicleMesh from the database to be used for route evaluation.

    The latest mesh containing all points in the route will be chosen.
    If no suitable VehicleMesh objects are available, return None.

    Args:
        route (dict): GeoJSON route to be evaluated.
        vehicle_type (str, optional): Specific vehicle type to look for.

    Returns:
        Union[list[VehicleMesh], None]: Selected VehicleMesh objects or None.
    """

    coordinates = route["features"][0]["geometry"]["coordinates"]
    lats = [c[0] for c in coordinates]
    lons = [c[1] for c in coordinates]

    # Use select_mesh with vehicle_type parameter, but specify vehicle type
    meshes = select_mesh(min(lats), min(lons), max(lats), max(lons), vehicle_type)

    if meshes:
        vehicle_meshes = [mesh for mesh in meshes if isinstance(mesh, VehicleMesh)]
        return vehicle_meshes if vehicle_meshes else None

    return None


def check_mesh_data(mesh: Union[EnvironmentMesh, VehicleMesh]) -> str:
    """Check a mesh object for missing data sources.

    Args:
        mesh (Union[EnvironmentMesh, VehicleMesh]): mesh object to evaluate.

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


def ingest_mesh(
    mesh_json: Dict[str, Any],
    mesh_filename: str,
    metadata_record: Dict[str, Any] = None,
    expected_md5: str = None,
) -> Tuple[Union[EnvironmentMesh, VehicleMesh], bool, str]:
    """
    Ingest a mesh into the database, automatically detecting mesh type.

    This function handles creating either EnvironmentMesh or VehicleMesh records
    based on the mesh content. For vehicle meshes, it automatically creates Vehicle
    records if they don't exist. It also calculates MD5 hash internally and optionally
    validates against expected MD5.

    Args:
        mesh_json (Dict[str, Any]): The mesh JSON
        mesh_filename (str): Name of the mesh file
        metadata_record (Dict[str, Any], optional): Metadata record from upload metadata
        expected_md5 (str, optional): Expected MD5 hash for validation

    Returns:
        Tuple[Union[EnvironmentMesh, VehicleMesh], bool, str]:
            - The created mesh object
            - Whether a new mesh was created (True) or existing found (False)
            - The mesh type ("EnvironmentMesh" or "VehicleMesh")

    Raises:
        ValueError: If vehicle mesh is missing required configuration or MD5 mismatch
        Exception: If vehicle creation fails
    """
    # Calculate MD5 hash from mesh JSON
    tfile = NamedTemporaryFile(mode="w+", delete=True)
    json.dump(mesh_json, tfile, indent=4)
    tfile.flush()
    md5 = calculate_md5(tfile.name)

    # Validate MD5 if expected hash is provided
    if expected_md5 and md5 != expected_md5:
        raise ValueError(f"Mesh MD5 {md5} does not match expected MD5 {expected_md5}")

    # Clean JSON data to handle NaN values and None in critical fields
    def clean_json_data(obj, path=""):
        """
        Recursively clean JSON data to replace NaN with None and handle None in critical fields.

        Args:
            obj: Object to clean
            path: Current path in the JSON structure (for debugging)
        """
        if isinstance(obj, dict):
            # Special handling for cellbox agg_data
            if "agg_data" in obj and isinstance(obj["agg_data"], dict):
                if obj["agg_data"].get("SIC") is None:
                    # SIC (Sea Ice Concentration): None -> 0.0 (no ice)
                    obj["agg_data"]["SIC"] = 0.0
                    logger.debug(f"Replaced None SIC value with 0.0 at {path}")

                if obj["agg_data"].get("thickness") is None:
                    obj["agg_data"]["thickness"] = 0.0

                if obj["agg_data"].get("density") is None:
                    obj["agg_data"]["density"] = 0.0

            # Special handling for cellboxes with direct SIC/thickness/density fields
            if "id" in obj and any(
                key in obj for key in ["SIC", "thickness", "density"]
            ):
                if obj.get("SIC") is None:
                    obj["SIC"] = 0.0
                    logger.debug(f"Replaced None SIC value with 0.0 at {path}")

                if obj.get("thickness") is None:
                    obj["thickness"] = 0.0

                if obj.get("density") is None:
                    obj["density"] = 0.0

            return {k: clean_json_data(v, f"{path}.{k}") for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_json_data(item, f"{path}[{i}]") for i, item in enumerate(obj)]
        elif isinstance(obj, float):
            import math

            if math.isnan(obj):
                return None
            elif math.isinf(obj):
                return None
            return obj
        return obj

    cleaned_mesh_json = clean_json_data(mesh_json)

    # Determine if this is a vehicle mesh or environment mesh
    is_vehicle_mesh = False
    vehicle_type = None

    config = cleaned_mesh_json.get("config", {})

    # Look for vessel configuration in the mesh
    if "vessel_info" in config:
        is_vehicle_mesh = True
        vessel_config = config["vessel_info"]
        vehicle_type = vessel_config.get("vessel_type")
        logger.info(f"Found vessel config with type: {vehicle_type}")

    mesh_type = "VehicleMesh" if is_vehicle_mesh else "EnvironmentMesh"
    logger.info(f"Processing {mesh_type}: {mesh_filename}")

    # Prepare mesh defaults
    if metadata_record:
        # Use metadata record for date and coordinate information
        mesh_defaults = {
            "name": mesh_filename,
            "valid_date_start": timezone.make_aware(
                datetime.strptime(
                    cleaned_mesh_json["config"]["mesh_info"]["region"]["start_time"],
                    "%Y-%m-%d",
                )
            ),
            "valid_date_end": timezone.make_aware(
                datetime.strptime(
                    cleaned_mesh_json["config"]["mesh_info"]["region"]["end_time"],
                    "%Y-%m-%d",
                )
            ),
            "created": timezone.make_aware(
                datetime.strptime(metadata_record["created"], "%Y%m%dT%H%M%S")
            ),
            "json": cleaned_mesh_json,
            "meshiphi_version": metadata_record["meshiphi"],
            "lat_min": metadata_record["latlong"]["latmin"],
            "lat_max": metadata_record["latlong"]["latmax"],
            "lon_min": metadata_record["latlong"]["lonmin"],
            "lon_max": metadata_record["latlong"]["lonmax"],
        }
    else:
        # Use mesh data for coordinate information (manual insertion)
        mesh_defaults = {
            "name": mesh_filename,
            "valid_date_start": timezone.make_aware(
                datetime.strptime(
                    cleaned_mesh_json["config"]["mesh_info"]["region"]["start_time"],
                    "%Y-%m-%d",
                )
            ),
            "valid_date_end": timezone.make_aware(
                datetime.strptime(
                    cleaned_mesh_json["config"]["mesh_info"]["region"]["end_time"],
                    "%Y-%m-%d",
                )
            ),
            "created": timezone.now(),
            "json": cleaned_mesh_json,
            "meshiphi_version": "manually_inserted",
            "lat_min": cleaned_mesh_json["config"]["mesh_info"]["region"]["lat_min"],
            "lat_max": cleaned_mesh_json["config"]["mesh_info"]["region"]["lat_max"],
            "lon_min": cleaned_mesh_json["config"]["mesh_info"]["region"]["long_min"],
            "lon_max": cleaned_mesh_json["config"]["mesh_info"]["region"]["long_max"],
        }

    if is_vehicle_mesh:
        if not vehicle_type:
            raise ValueError(
                "Vehicle mesh found but no vessel_type specified in config"
            )

        # For vehicle meshes, we need to determine the vehicle type
        try:
            vehicle = Vehicle.objects.get(vessel_type=vehicle_type)
            logger.info(f"Found existing vehicle type '{vehicle_type}' in database")
        except Vehicle.DoesNotExist:
            logger.info(
                f"Vehicle type '{vehicle_type}' not found in database, creating new vehicle"
            )

            # Get vessel config
            vessel_config = config.get("vessel_info", {})

            # Extract required fields from vessel config
            max_speed = vessel_config.get("max_speed")
            unit = vessel_config.get("unit")

            if not max_speed or not unit:
                raise ValueError(
                    f"Vehicle mesh missing required fields: max_speed={max_speed}, unit={unit}"
                )

            # Create new Vehicle from vessel config
            vehicle_data = {
                "vessel_type": vehicle_type,
                "max_speed": max_speed,
                "unit": unit,
                "created": timezone.now(),
            }

            # Add optional fields if they exist in the vessel config
            optional_fields = [
                "max_ice_conc",
                "min_depth",
                "max_wave",
                "excluded_zones",
                "neighbour_splitting",
                "beam",
                "hull_type",
                "force_limit",
            ]

            for field in optional_fields:
                if field in vessel_config:
                    vehicle_data[field] = vessel_config[field]

            try:
                vehicle = Vehicle.objects.create(**vehicle_data)
                logger.info(f"Created new vehicle '{vehicle_type}' in database")
            except Exception as e:
                raise Exception(f"Failed to create vehicle '{vehicle_type}': {e}")

        # Create VehicleMesh
        mesh_defaults["vehicle"] = vehicle
        mesh_defaults["environment_mesh"] = None

        mesh, created = VehicleMesh.objects.get_or_create(
            md5=md5, defaults=mesh_defaults
        )
    else:
        # Create EnvironmentMesh
        mesh, created = EnvironmentMesh.objects.get_or_create(
            md5=md5, defaults=mesh_defaults
        )

    return mesh, created, mesh_type


def optimise_route(mesh_json: dict, route) -> list:
    """
    Calculate optimal route using PolarRoute.

    This function performs the core route optimization using PolarRoute's RoutePlanner.
    Requires a VehicleMesh.

    Args:
        mesh_json (dict): Vehicle mesh
        route (Route): Route database object with start/end coordinates and metadata

    Returns:
        smoothed routes as list of geojson dictionaries
    """
    logger.info(f"Calculating route optimization for route {route.id}")

    # Detect energy source based on vehicle type using configuration
    vehicle = route.vehicle

    # Get energy source from settings configuration
    energy_source = settings.VEHICLE_ENERGY_SOURCES.get(
        vehicle.vessel_type, settings.DEFAULT_ENERGY_SOURCE
    )

    logger.info(f"Detected energy source in mesh: {energy_source}")

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

    # Select the appropriate energy config based on detected energy source
    if energy_source == "fuel":
        energy_config = settings.FUEL_CONFIG
    elif energy_source == "battery":
        energy_config = settings.BATTERY_CONFIG
    else:
        raise ValueError(f"Unsupported energy source: {energy_source}")

    configs = (
        settings.TRAVELTIME_CONFIG,
        energy_config,
    )

    for config in configs:
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

    # Update route with unsmoothed data
    route.json_unsmoothed = unsmoothed_routes
    route.calculated = timezone.now()
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


def add_vehicle_to_environment_mesh(environment_mesh, vehicle):
    """
    Create a VehicleMesh by adding vehicle to an EnvironmentMesh.

    Args:
        environment_mesh (EnvironmentMesh): EnvironmentMesh
        vehicle (Vehicle): Vehicle object

    Returns:
        VehicleMesh: Newly created VehicleMesh

    Raises:
        RuntimeError: If vessel addition fails
    """
    logger.info(
        f"Adding vehicle {vehicle.vessel_type} to environment mesh {environment_mesh.id}"
    )

    # Create vehicle config dictionary from Vehicle model
    vehicle_config = {
        "vessel_type": vehicle.vessel_type,
        "max_speed": vehicle.max_speed,
        "unit": vehicle.unit,
    }

    # Add optional vehicle properties if they exist
    optional_fields = [
        "max_ice_conc",
        "min_depth",
        "max_wave",
        "excluded_zones",
        "neighbour_splitting",
        "beam",
        "hull_type",
        "force_limit",
    ]

    for field in optional_fields:
        value = getattr(vehicle, field, None)
        if value is not None:
            vehicle_config[field] = value

    try:
        # Clean the environment mesh data before processing to handle None values
        def clean_mesh_data(obj, path=""):
            """Clean mesh data to handle None values in critical fields."""
            if isinstance(obj, dict):
                if "agg_data" in obj and isinstance(obj["agg_data"], dict):
                    if obj["agg_data"].get("SIC") is None:
                        obj["agg_data"]["SIC"] = 0.0
                        logger.debug(f"Replaced None SIC value with 0.0 at {path}")
                    if obj["agg_data"].get("thickness") is None:
                        obj["agg_data"]["thickness"] = 0.0
                    if obj["agg_data"].get("density") is None:
                        obj["agg_data"]["density"] = 0.0

                if "id" in obj and any(
                    key in obj for key in ["SIC", "thickness", "density"]
                ):
                    if obj.get("SIC") is None:
                        obj["SIC"] = 0.0
                        logger.debug(f"Replaced None SIC value with 0.0 at {path}")
                    if obj.get("thickness") is None:
                        obj["thickness"] = 0.0
                    if obj.get("density") is None:
                        obj["density"] = 0.0

                return {k: clean_mesh_data(v, f"{path}.{k}") for k, v in obj.items()}
            elif isinstance(obj, list):
                return [
                    clean_mesh_data(item, f"{path}[{i}]") for i, item in enumerate(obj)
                ]
            elif isinstance(obj, float):
                import math

                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            return obj

        cleaned_mesh_json = clean_mesh_data(copy.deepcopy(environment_mesh.json))

        # Use VesselPerformanceModeller to add vehicle performance to the mesh
        logger.info(f"Running vessel performance modelling for {vehicle.vessel_type}")

        # Try to initialize with the vessel_type first
        try:
            vp = VesselPerformanceModeller(
                env_mesh_json=cleaned_mesh_json, vessel_config=vehicle_config
            )
        except ValueError as e:
            if "not in known list of vessels" in str(e):
                # If vessel type is not recognized, use custom_vessel with ExampleShip as base
                logger.info(
                    f"Vessel type '{vehicle.vessel_type}' does not have a performance model in PolarRoute {polar_route.__version__}, using ExampleShip as base model"
                )
                vp = VesselPerformanceModeller(
                    env_mesh_json=cleaned_mesh_json,
                    vessel_config=vehicle_config,
                    custom_vessel=ExampleShip,
                )
            else:
                raise

        # Model accessibility (determines which cells are accessible to this vessel)
        vp.model_accessibility()

        # Model performance (calculates vessel-specific performance metrics)
        vp.model_performance()

        # Get the modified mesh with vessel performance data
        vessel_mesh_json = vp.to_json()

        logger.info(f"Vessel performance modelling completed for {vehicle.vessel_type}")

    except Exception as e:
        logger.error(f"Error during vessel performance modelling: {e}")
        raise RuntimeError(
            f"Failed to create vehicle mesh for {vehicle.vessel_type}: {e}"
        )

    # Calculate MD5 for the processed vessel mesh data
    tfile = NamedTemporaryFile(mode="w+", delete=True)
    json.dump(vessel_mesh_json, tfile, indent=4)
    tfile.flush()
    vehicle_mesh_md5 = calculate_md5(tfile.name)

    # Import here to avoid circular imports
    from .models import VehicleMesh

    # Create vehicle mesh by copying environment mesh metadata and updating with vessel data
    vehicle_mesh = VehicleMesh.objects.create(
        environment_mesh=environment_mesh,
        vehicle=vehicle,
        meshiphi_version=environment_mesh.meshiphi_version,
        md5=vehicle_mesh_md5,
        valid_date_start=environment_mesh.valid_date_start,
        valid_date_end=environment_mesh.valid_date_end,
        created=timezone.now(),
        lat_min=environment_mesh.lat_min,
        lat_max=environment_mesh.lat_max,
        lon_min=environment_mesh.lon_min,
        lon_max=environment_mesh.lon_max,
        name=f"{environment_mesh.name}_vehicle_{vehicle.vessel_type}",
        json=vessel_mesh_json,
    )

    logger.info(
        f"Created VehicleMesh {vehicle_mesh.id} for vehicle {vehicle.vessel_type}"
    )
    return vehicle_mesh
