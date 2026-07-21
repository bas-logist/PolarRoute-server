import copy
import datetime
import gzip
import json
from pathlib import Path
import tempfile
import os
import re

from celery import states
from celery.exceptions import Ignore
from celery.utils.log import get_task_logger
from django.conf import settings
from django.utils import timezone
import numpy as np
import pandas as pd
import polar_route
from polar_route.route_planner.route_planner import RoutePlanner
from polar_route.utils import extract_geojson_routes
import yaml

from polarrouteserver.celery import app
from .models import Job, Mesh, Route
from .utils import calculate_md5, check_mesh_data

VESSEL_MESH_FILENAME_PATTERN = re.compile(r"vessel_?.*\.json$")

logger = get_task_logger(__name__)


@app.task(bind=True)
def optimise_route(
    self,
    route_id: int,
    backup_mesh_ids: list[int] = None,
) -> dict:
    """
    Use PolarRoute to calculate optimal route from Route database object and mesh.
    Saves Route in database and returns route geojson as dictionary.

    Params:
        route_id: id of record in Route database table
        backup_mesh_ids list: list of database ids of backup meshes to try in order of priority

    Returns:
        route geojson as dictionary
    """
    route = Route.objects.get(id=route_id)
    mesh = route.mesh
    logger.info(f"Running optimisation for route {route.id}")
    logger.info(f"Using mesh {mesh.id}")
    if backup_mesh_ids:
        logger.info(f"Also got backup mesh ids {backup_mesh_ids}")

    # add warning on mesh date if older than today
    if mesh.created.date() < datetime.datetime.now().date():
        route.info = {
            "info": f"Latest available mesh from {datetime.datetime.strftime(mesh.created, '%Y/%m/%d %H:%M%S')}"
        }

    data_warning_message = check_mesh_data(mesh)
    if data_warning_message != "":
        if route.info is None:
            route.info = {"info": data_warning_message}
        else:
            route.info["info"] = route.info["info"] + data_warning_message

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

    try:
        unsmoothed_routes = []
        route_planners = []
        configs = (
            settings.TRAVELTIME_CONFIG,
            settings.FUEL_CONFIG,
        )
        for config in configs:
            rp = RoutePlanner(copy.deepcopy(mesh.json), config)

            # Calculate optimal dijkstra path between waypoints
            rp.compute_routes(waypoints)

            route_planners.append(rp)

            # save the initial unsmoothed route
            logger.info(
                f"Calculating unsmoothed Dijkstra paths for {config['objective_function']}-optimised route."
            )
            if len(rp.routes_dijkstra) == 0:
                raise ValueError("Inaccessible. No routes found.")
            route_geojson = extract_geojson_routes(rp.to_json())
            route_geojson[0]["features"][0]["properties"]["objective_function"] = (
                config["objective_function"]
            )
            unsmoothed_routes.append(route_geojson)

        # Save unsmoothed routes (but don't set calculated timestamp yet)
        route.json_unsmoothed = unsmoothed_routes
        route.polar_route_version = polar_route.__version__
        route.save()  # Save progress but no calculated timestamp

        smoothed_routes = []
        for i, rp in enumerate(route_planners):
            # Smooth the dijkstra routes
            rp.compute_smoothed_routes()
            # Save the smoothed route(s)
            logger.info(f"Route smoothing {i + 1}/{len(route_planners)} complete.")
            route_geojson = extract_geojson_routes(rp.to_json())
            route_geojson[0]["features"][0]["properties"]["objective_function"] = (
                rp.config["objective_function"]
            )
            smoothed_routes.append(route_geojson)

        # Update the database with all routes at once
        route.json = smoothed_routes

        # Set calculated timestamp when all routes ready
        route.calculated = timezone.now()
        route.polar_route_version = polar_route.__version__
        route.save()

        return smoothed_routes

    except Exception as e:
        logger.error(e)
        self.update_state(state=states.FAILURE)
        # this is awful, polar route should raise a custom error class
        if "Inaccessible. No routes found" in e.args[0] and len(backup_mesh_ids) > 0:
            # if route is inaccesible in the mesh, try again if backup meshes are provided
            logger.info(
                f"No routes found on mesh {mesh.id}, trying with next mesh(es) {backup_mesh_ids}"
            )
            route.info = {"info": "Route inaccessible on mesh, trying next mesh."}
            route.mesh = Mesh.objects.get(id=backup_mesh_ids[0])
            route.save()
            task = optimise_route.delay(route.id, backup_mesh_ids[1:])
            _ = Job.objects.create(
                id=task.id,
                route=route,
            )
            raise Ignore()
        else:
            route.info = {"error": f"{e}"}
            route.save()
            raise Ignore()


@app.task(bind=True)
def import_new_meshes(self):
    """Look for new meshes and insert them into the database."""

    if settings.MESH_METADATA_DIR is None:
        raise ValueError("MESH_METADATA_DIR has not been set.")

    # find the latest metadata file
    files = os.listdir(settings.MESH_METADATA_DIR)
    file_list = [
        os.path.join(settings.MESH_METADATA_DIR, file)
        for file in files
        if file.startswith("upload_metadata") and file.endswith(".yaml.gz")
    ]
    if len(file_list) == 0:
        msg = "Upload metadata file not found."
        logger.error(msg)
        return
    latest_metadata_file = max(file_list, key=os.path.getctime)

    # load in the metadata
    logger.info(
        f"Loading metadata file from {os.path.join(settings.MESH_METADATA_DIR, latest_metadata_file)}"
    )
    with gzip.open(latest_metadata_file, "rb") as f:
        metadata = yaml.load(f.read(), Loader=yaml.Loader)

    meshes_added = []
    for record in metadata["records"]:
        # we only want the vessel json files
        if not bool(re.search(VESSEL_MESH_FILENAME_PATTERN, record["filepath"])):
            continue

        # extract the filename from the filepath
        mesh_filename = record["filepath"].split("/")[-1]

        # load in the mesh json
        try:
            zipped_filename = mesh_filename + ".gz"
            with gzip.open(
                Path(settings.MESH_DIR, zipped_filename), "rb"
            ) as gzipped_mesh:
                mesh_json = json.load(gzipped_mesh)
        except FileNotFoundError:
            logger.warning(f"{zipped_filename} not found. Skipping.")
            continue
        except PermissionError:
            logger.warning(
                f"Can't read {zipped_filename} due to permission error. File may still be transferring. Skipping."
            )
            continue

        # write out the unzipped mesh to temp file
        tfile = tempfile.NamedTemporaryFile(mode="w+", delete=True)
        json.dump(mesh_json, tfile, indent=4)
        tfile.flush()
        md5 = calculate_md5(tfile.name)

        # cross reference md5 hash from file record in metadata to actual file on disk
        if md5 != record["md5"]:
            logger.warning(
                f"Mesh file md5: {md5}\n\
                           does not match\n\
                           Metadata md5: {record['md5']}\n\
                           Skipping."
            )
            # if md5 hash from metadata file does not match that of the file itself,
            # there may have been a filename clash, skip this one.
            continue

        # create an entry in the database
        mesh, created = Mesh.objects.get_or_create(
            md5=md5,
            defaults={
                "name": mesh_filename,
                "valid_date_start": datetime.datetime.strptime(
                    mesh_json["config"]["mesh_info"]["region"]["start_time"], "%Y-%m-%d"
                ).replace(tzinfo=datetime.timezone.utc),
                "valid_date_end": datetime.datetime.strptime(
                    mesh_json["config"]["mesh_info"]["region"]["end_time"], "%Y-%m-%d"
                ).replace(tzinfo=datetime.timezone.utc),
                "created": datetime.datetime.strptime(
                    record["created"], "%Y%m%dT%H%M%S"
                ).replace(tzinfo=datetime.timezone.utc),
                "json": mesh_json,
                "meshiphi_version": record["meshiphi"],
                "lat_min": record["latlong"]["latmin"],
                "lat_max": record["latlong"]["latmax"],
                "lon_min": record["latlong"]["lonmin"],
                "lon_max": record["latlong"]["lonmax"],
            },
        )
        if created:
            logger.info(
                f"Adding new mesh to database: {mesh.id} {mesh.name} {mesh.created}"
            )
            meshes_added.append(
                {"id": mesh.id, "md5": record["md5"], "name": mesh.name}
            )

    return meshes_added


@app.task(bind=True)
def cleanup_routes(self):
    # catch any unexpected error where this task is called without the correct setting, this shouldn't happen, but protects against unintented use of this destructive method
    if not settings.CLEANUP_ROUTES:
        raise Exception(
            "cleanup_routes has been executed but the CLEANUP_ROUTES setting is not True. Exiting."
        )

    time_threshold = timezone.now() - datetime.timedelta(
        days=settings.CLEANUP_ROUTES_DAYS
    )
    routes_to_delete = Route.objects.filter(
        calculated__lt=time_threshold, protect=False
    )
    routes_to_delete.delete()


@app.task(bind=True)
def cleanup_meshes(self):
    # catch any unexpected error where this task is called without the correct setting, this shouldn't happen, but protects against unintented use of this destructive method
    if not settings.CLEANUP_MESHES:
        raise Exception(
            "cleanup_meshes has been executed but the CLEANUP_MESHES setting is not True. Exiting."
        )

    time_threshold = timezone.now() - datetime.timedelta(
        days=settings.CLEANUP_MESHES_DAYS
    )
    meshes_to_delete = Mesh.objects.filter(created__lt=time_threshold, protect=False)
    meshes_to_delete.delete()
