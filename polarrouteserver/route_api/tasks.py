import datetime
import gzip
import json
from pathlib import Path
import os
import re

from celery import states
from celery.exceptions import Ignore
from celery.utils.log import get_task_logger
from django.conf import settings
import yaml

from polarrouteserver.celery import app
from .models import Job, Route, VehicleMesh, EnvironmentMesh, Vehicle
from .utils import (
    check_mesh_data,
    ingest_mesh,
    optimise_route,
    add_vehicle_to_environment_mesh,
)

VESSEL_MESH_FILENAME_PATTERN = re.compile(r"vessel_?.*\.json$")

logger = get_task_logger(__name__)


@app.task(bind=True)
def import_new_meshes(self):
    """
    Look for new meshes and insert them into the database.

    Automatically detects whether each mesh is an EnvironmentMesh or VehicleMesh based
    on mesh content.

    For VehicleMesh files:
    - Extracts vehicle configuration from mesh data.
    - Creates Vehicle records if they don't exist in database.
    - Links VehicleMesh to corresponding Vehicle.

    For EnvironmentMesh files:
    - Creates EnvironmentMesh record.

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

    # Filter records to only process vessel json files
    vessel_records = [
        record
        for record in metadata["records"]
        if bool(re.search(VESSEL_MESH_FILENAME_PATTERN, record["filepath"]))
    ]

    total_meshes = len(vessel_records)
    logger.info(f"Found {total_meshes} mesh files to process")

    # Update initial state
    self.update_state(
        state="STARTED",
        meta={"current": 0, "total": total_meshes, "status": "Starting mesh import..."},
    )

    for i, record in enumerate(vessel_records, 1):
        # Extract the filename from the filepath
        mesh_filename = record["filepath"].split("/")[-1]

        # Update progress
        self.update_state(
            state="PROCESSING",
            meta={
                "current": i,
                "total": total_meshes,
                "status": f"Processing mesh {i}/{total_meshes}: {mesh_filename}",
            },
        )

        # Load in the mesh json
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

        # Use the ingest_mesh utility function to handle mesh creation
        try:
            mesh, created, mesh_type = ingest_mesh(
                mesh_json=mesh_json,
                mesh_filename=mesh_filename,
                metadata_record=record,
                expected_md5=record["md5"],
            )
        except ValueError as e:
            logger.warning(f"MD5 validation failed for {mesh_filename}: {e}. Skipping.")
            continue
        except Exception as e:
            logger.error(f"Failed to ingest mesh {mesh_filename}: {e}")
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
        else:
            logger.info(
                f"Mesh {mesh_filename} already exists in database (MD5: {record['md5']})"
            )

    # Update final state
    self.update_state(
        state="SUCCESS",
        meta={
            "current": total_meshes,
            "total": total_meshes,
            "status": f"Completed! Added {len(meshes_added)} new meshes to database",
        },
    )

    return meshes_added


@app.task(bind=True)
def create_and_calculate_route(
    self,
    route_id: int,
    vehicle_type: str = None,
    backup_mesh_ids: list[int] = None,
) -> dict:
    """
    Calculate optimal route using VehicleMesh, creating one if necessary.

    This is the main route calculation task that ensures the correct VehicleMesh is used
    for the requested vehicle type. Routes can ONLY be calculated with VehicleMesh
    (never EnvironmentMesh alone).

    Workflow:
    1. Validates that vehicle_type is provided (required for route calculation)
    2. Determines current mesh type (VehicleMesh or EnvironmentMesh)
    3. If VehicleMesh exists but for wrong vehicle: finds/creates correct VehicleMesh
    4. If EnvironmentMesh: creates VehicleMesh for requested vehicle
    5. Performs route optimization using the correct VehicleMesh
    6. Handles backup meshes if route is inaccessible

    Args:
        route_id (int): Database ID of Route record to calculate
        vehicle_type (str): Vessel type for route calculation (required)
        backup_mesh_ids (list[int], optional): List of backup mesh IDs to try if
                                             main mesh yields no accessible routes

    Returns:
        dict: Route GeoJSON data with optimized routes

    Raises:
        ValueError: If vehicle_type not provided or vehicle not found in database
        RuntimeError: If VehicleMesh creation fails
    """
    route = Route.objects.get(id=route_id)
    logger.info(f"Running route optimization for route {route.id}")

    self.update_state(
        state="STARTED",
        meta={"status": f"Starting route calculation for route {route.id}"},
    )

    # Routes MUST have a vehicle type to be calculated
    if not vehicle_type:
        raise ValueError("vehicle_type is required for route calculation")

    try:
        vehicle = Vehicle.objects.get(vessel_type=vehicle_type)
    except Vehicle.DoesNotExist:
        raise ValueError(f"Vehicle type '{vehicle_type}' not found in database")

    current_mesh = route.mesh

    self.update_state(
        state="PROGRESS",
        meta={"status": f"Preparing mesh for vehicle type: {vehicle_type}"},
    )

    # Check the type of mesh we have and handle accordingly
    if isinstance(current_mesh, VehicleMesh):
        # Check if it matches the requested vehicle type
        if current_mesh.vehicle == vehicle:
            logger.info(
                f"Using existing VehicleMesh {current_mesh.id} for vehicle {vehicle_type}"
            )
            vehicle_mesh = current_mesh
        else:
            # VehicleMesh exists but for wrong vehicle - get the EnvironmentMesh and create correct VehicleMesh
            logger.info(
                f"Current VehicleMesh {current_mesh.id} is for '{current_mesh.vehicle.vessel_type}' but '{vehicle_type}' was requested"
            )

            # Get the underlying EnvironmentMesh
            environment_mesh = current_mesh.environment_mesh

            # Create new VehicleMesh for this vehicle + environment
            logger.info(
                f"Creating new VehicleMesh for vehicle {vehicle_type} using EnvironmentMesh {environment_mesh.id}"
            )

            self.update_state(
                state="PROGRESS",
                meta={"status": f"Creating VehicleMesh for vehicle {vehicle_type}"},
            )

            vehicle_mesh = add_vehicle_to_environment_mesh(environment_mesh, vehicle)

            # Update route to use the correct VehicleMesh
            route.mesh = vehicle_mesh
            route.save()

    elif isinstance(current_mesh, EnvironmentMesh):
        # Need to create VehicleMesh for the requested vehicle
        logger.info(
            f"Route has EnvironmentMesh {current_mesh.id}, creating VehicleMesh for vehicle {vehicle_type}"
        )

        # Create new VehicleMesh for this vehicle
        logger.info(
            f"Creating new VehicleMesh for vehicle {vehicle_type} using EnvironmentMesh {current_mesh.id}"
        )
        self.update_state(
            state="PROGRESS",
            meta={"status": f"Creating VehicleMesh for vehicle {vehicle_type}"},
        )
        vehicle_mesh = add_vehicle_to_environment_mesh(current_mesh, vehicle)

        # Update route to use the VehicleMesh
        route.mesh = vehicle_mesh
        route.save()
    else:
        # Unknown mesh type
        raise ValueError(f"Unexpected mesh type: {type(current_mesh)}")

    # Now we have the correct VehicleMesh for route calculation
    mesh = vehicle_mesh

    # Update progress
    self.update_state(
        state="PROGRESS",
        meta={
            "status": "Checking mesh data quality and performing route optimization..."
        },
    )

    # Add warning on mesh date if older than today
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

    try:
        # Update progress before starting route calculation
        self.update_state(
            state="PROGRESS",
            meta={"status": "Running PolarRoute optimization algorithm..."},
        )

        # Use the non-task function to calculate the route
        smoothed_routes = optimise_route(mesh.json, route)

        # Update final progress
        self.update_state(
            state="SUCCESS",
            meta={"status": "Route optimization completed successfully"},
        )

        return smoothed_routes

    except Exception as e:
        logger.error(e)
        self.update_state(state=states.FAILURE)

        # Check if this is an inaccessible route error and we have backup meshes
        if "Inaccessible. No routes found" in str(e) and backup_mesh_ids:
            logger.info(
                f"No routes found on mesh {mesh.id}, trying with next mesh(es) {backup_mesh_ids}"
            )
            self.update_state(
                state="RETRY",
                meta={
                    "status": "Route inaccessible on current mesh, trying backup mesh..."
                },
            )
            route.info = {"info": "Route inaccessible on mesh, trying next mesh."}

            try:
                backup_mesh_id = backup_mesh_ids[0]

                # Try to get backup mesh as VehicleMesh first
                try:
                    backup_vehicle_mesh = VehicleMesh.objects.get(id=backup_mesh_id)

                    # Check if this VehicleMesh is for the correct vehicle
                    if backup_vehicle_mesh.vehicle == vehicle:
                        logger.info(
                            f"Using backup VehicleMesh {backup_mesh_id} for vehicle {vehicle_type}"
                        )
                        route.mesh = backup_vehicle_mesh
                        route.save()
                    else:
                        # VehicleMesh exists but for wrong vehicle - get the EnvironmentMesh and create correct VehicleMesh
                        backup_environment_mesh = backup_vehicle_mesh.environment_mesh
                        if not backup_environment_mesh:
                            raise ValueError(
                                f"Backup VehicleMesh {backup_mesh_id} has no associated EnvironmentMesh"
                            )

                        # Check if correct VehicleMesh already exists
                        correct_vehicle_mesh = VehicleMesh.objects.filter(
                            vehicle=vehicle, environment_mesh=backup_environment_mesh
                        ).first()

                        if correct_vehicle_mesh:
                            logger.info(
                                f"Using existing VehicleMesh {correct_vehicle_mesh.id} for backup"
                            )
                            route.mesh = correct_vehicle_mesh
                            route.save()
                        else:
                            # Create new VehicleMesh for backup
                            logger.info(
                                f"Creating VehicleMesh for vehicle {vehicle_type} from backup EnvironmentMesh {backup_environment_mesh.id}"
                            )
                            new_vehicle_mesh = add_vehicle_to_environment_mesh(
                                backup_environment_mesh, vehicle
                            )
                            route.mesh = new_vehicle_mesh
                            route.save()

                except VehicleMesh.DoesNotExist:
                    # Try as EnvironmentMesh
                    try:
                        backup_environment_mesh = EnvironmentMesh.objects.get(
                            id=backup_mesh_id
                        )

                        # Check if VehicleMesh already exists for this combination
                        existing_vehicle_mesh = VehicleMesh.objects.filter(
                            vehicle=vehicle, environment_mesh=backup_environment_mesh
                        ).first()

                        if existing_vehicle_mesh:
                            logger.info(
                                f"Using existing VehicleMesh {existing_vehicle_mesh.id} for backup"
                            )
                            route.mesh = existing_vehicle_mesh
                            route.save()
                        else:
                            # Create VehicleMesh for backup EnvironmentMesh
                            logger.info(
                                f"Creating VehicleMesh for vehicle {vehicle_type} from backup EnvironmentMesh {backup_mesh_id}"
                            )
                            new_vehicle_mesh = add_vehicle_to_environment_mesh(
                                backup_environment_mesh, vehicle
                            )
                            route.mesh = new_vehicle_mesh
                            route.save()

                    except EnvironmentMesh.DoesNotExist:
                        raise ValueError(f"Backup mesh {backup_mesh_id} not found")

                # Retry with the backup mesh
                task = create_and_calculate_route.delay(
                    route.id, vehicle_type, backup_mesh_ids[1:]
                )
                _ = Job.objects.create(
                    id=task.id,
                    route=route,
                )
                raise Ignore()

            except (ValueError, RuntimeError) as backup_error:
                logger.error(
                    f"Error with backup mesh {backup_mesh_ids[0]}: {backup_error}"
                )
                route.info = {"error": "No accessible mesh found for route calculation"}
                route.save()
                raise e
        else:
            route.info = {"error": str(e)}
            route.save()
            raise Ignore()
