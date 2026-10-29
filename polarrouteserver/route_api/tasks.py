import datetime
import gzip
import json
import os
import re
from pathlib import Path

import yaml
from celery import states
from celery.exceptions import Ignore
from celery.utils.log import get_task_logger
from django.conf import settings
from django.utils import timezone

from polarrouteserver.celery import app

from .models import Job, Mesh, Route
from .utils import (
    NotAMeshError,
    check_mesh_data,
    check_missing_ice_data,
    get_vehicle_mesh,
    ingest_mesh,
    optimise_route,
)

MESH_FILENAME_PATTERN = re.compile(r"\.json$")

logger = get_task_logger(__name__)


@app.task(bind=True)
def import_new_meshes(self):
    """
    Look for new meshes and insert them into the database.

    Automatically detects whether each mesh is an EnvironmentMesh or VehicleMesh based
    on mesh content. Vehicles are created for VehicleMeshes if they don't exist.

    Returns:
        list: List of dictionaries containing details of added meshes with fields:
              - id: Database ID of created mesh
              - md5: MD5 hash of mesh data
              - name: Mesh filename
              - type: "VehicleMesh" or "EnvironmentMesh"

    Raises:
        ValueError: If MESH_METADATA_DIR is not set
    """

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
        if not re.search(MESH_FILENAME_PATTERN, record["filepath"]):
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
        except (OSError, EOFError, ValueError) as e:
            logger.warning(
                f"Can't read {zipped_filename}: {e}. File may still be transferring. Skipping."
            )
            continue

        # cross reference md5 hash from file record in metadata to actual file on disk,
        # if they do not match there may have been a filename clash, skip this one.
        try:
            mesh, created, mesh_type = ingest_mesh(
                mesh_json=mesh_json,
                mesh_filename=mesh_filename,
                metadata_record=record,
                expected_md5=record["md5"],
            )
        except NotAMeshError as e:
            logger.debug(f"Skipping {mesh_filename}: {e}")
            continue
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Skipping {mesh_filename}: {e!r}")
            continue

        if created:
            logger.info(
                f"Adding new {mesh_type} to database: {mesh.id} {mesh.name} {mesh.created}"
            )
            meshes_added.append(
                {
                    "id": mesh.id,
                    "md5": record["md5"],
                    "name": mesh.name,
                    "type": mesh_type,
                }
            )

    return meshes_added


@app.task(bind=True)
def create_and_calculate_route(
    self,
    route_id: int,
    backup_mesh_ids: list[int] | None = None,
) -> list:
    """
    Calculate optimal routes for a Route on a mesh with the performance of its vehicle.

    The mesh of the route is an EnvironmentMesh, or a VehicleMesh imported for the route's
    vehicle. The VehicleMesh for the route's vehicle is found, or built from the
    EnvironmentMesh if it doesn't exist yet.

    Saves Route in database and returns the smoothed routes as geojson dictionaries.

    Args:
        route_id: id of record in Route database table
        backup_mesh_ids: database ids of backup meshes to try in order of priority,
            if the route is inaccessible on the mesh.
    """
    route = Route.objects.get(id=route_id)
    logger.info(f"Running optimisation for route {route.id}")
    logger.info(f"Using mesh {route.mesh_id} for vehicle {route.vehicle_id}")
    if backup_mesh_ids:
        logger.info(f"Also got backup mesh ids {backup_mesh_ids}")

    try:
        mesh = get_vehicle_mesh(route.mesh, route.vehicle)
        route.vehicle_mesh = mesh

        # add warning on mesh date if older than today
        if mesh.created.date() < datetime.datetime.now(tz=datetime.UTC).date():
            route.info = {
                "info": f"Latest available mesh from {datetime.datetime.strftime(mesh.created, '%Y/%m/%d %H:%M%S')}"
            }

        data_warning_message = check_mesh_data(mesh) + check_missing_ice_data(mesh)
        if data_warning_message != "":
            if route.info is None:
                route.info = {"info": data_warning_message}
            else:
                route.info["info"] = route.info["info"] + data_warning_message

        return optimise_route(mesh.json, route)

    except Exception as e:  # noqa BLE001
        logger.error(e)
        self.update_state(state=states.FAILURE)
        # this is awful, polar route should raise a custom error class
        if "Inaccessible. No routes found" in str(e) and backup_mesh_ids:
            # if route is inaccesible in the mesh, try again if backup meshes are provided
            logger.info(
                f"No routes found on mesh {route.mesh_id}, trying with next mesh(es) {backup_mesh_ids}"
            )
            route.info = {"info": "Route inaccessible on mesh, trying next mesh."}
            route.mesh = Mesh.objects.get(id=backup_mesh_ids[0])
            route.save()
            task = create_and_calculate_route.delay(route.id, backup_mesh_ids[1:])
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
def cleanup_routes(self):
    # catch any unexpected error where this task is called without the correct setting, this shouldn't happen, but protects against unintented use of this destructive method
    if not settings.CLEANUP_ROUTES:
        raise RuntimeWarning(
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
        raise RuntimeWarning(
            "cleanup_meshes has been executed but the CLEANUP_MESHES setting is not True. Exiting."
        )

    time_threshold = timezone.now() - datetime.timedelta(
        days=settings.CLEANUP_MESHES_DAYS
    )
    # a built vehicle mesh is deleted with its environment mesh, unless it is protected
    meshes_to_delete = Mesh.objects.filter(
        created__lt=time_threshold, protect=False
    ).exclude(environmentmesh__vehiclemesh__protect=True)
    meshes_to_delete.delete()
