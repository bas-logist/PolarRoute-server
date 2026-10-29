import gzip
import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from polarrouteserver.route_api.utils import ingest_mesh


class Command(BaseCommand):
    help = "Manually insert a Mesh (or sequence of meshes) into the database.\n\
            Automatically detects whether each mesh is an EnvironmentMesh or VehicleMesh.\n\
            Takes json files or json files compressed gzip archives."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("meshes", nargs="+", type=str)

    def handle(self, *args: Any, **options: Any) -> str | None:
        for filepath in options["meshes"]:
            if filepath.endswith(".gz"):
                with gzip.open(filepath, "rb") as f:
                    mesh_json = json.load(f)
            else:
                with open(filepath, "r") as f:
                    mesh_json = json.load(f)

            # Extract filename from filepath
            mesh_filename = filepath.split("/")[-1]

            # Use the ingest_mesh utility function to handle mesh creation
            try:
                mesh, created, mesh_type = ingest_mesh(
                    mesh_json=mesh_json,
                    mesh_filename=mesh_filename,
                    metadata_record=None,  # No metadata record for manual insertion
                )
            except ValueError as e:
                raise CommandError(str(e))
            except Exception as e:
                raise CommandError(f"Failed to ingest mesh {mesh_filename}: {e}")

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{mesh_type} inserted: name: {mesh.name} \nmd5: {mesh.md5} \
                            \nid: {mesh.id} \
                            \ncreated: {mesh.created} \
                            \nlat: {mesh.lat_min}:{mesh.lat_max}\
                            \nlon: {mesh.lon_min}:{mesh.lon_max}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.NOTICE(
                        f"{mesh_type} with md5: {mesh.md5} already in database. No new records created."
                    )
                )
