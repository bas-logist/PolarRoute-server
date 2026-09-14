import gzip
import hashlib
import json
from datetime import datetime, timezone as tz
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from polarrouteserver.route_api.models import Mesh


class Command(BaseCommand):
    help = "Manually insert a Vessel Mesh (or sequence of meshes) into the database.\n\
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

            md5 = hashlib.md5(str(mesh_json).encode("utf-8")).hexdigest()

            if mesh_json["config"].get("vessel_info", None) is None:
                raise CommandError(
                    "vessel key not found in file, are you sure this is a vessel mesh?"
                )

            mesh, created = Mesh.objects.get_or_create(
                md5=md5,
                defaults={
                    "name": filepath.split("/")[-1],
                    "valid_date_start": datetime.strptime(
                        mesh_json["config"]["mesh_info"]["region"]["start_time"],
                        "%Y-%m-%d",
                    ).replace(tzinfo=tz.utc),
                    "valid_date_end": datetime.strptime(
                        mesh_json["config"]["mesh_info"]["region"]["end_time"],
                        "%Y-%m-%d",
                    ).replace(tzinfo=tz.utc),
                    "created": timezone.now(),
                    "json": mesh_json,
                    "meshiphi_version": "not found",
                    "lat_min": mesh_json["config"]["mesh_info"]["region"]["lat_min"],
                    "lat_max": mesh_json["config"]["mesh_info"]["region"]["lat_max"],
                    "lon_min": mesh_json["config"]["mesh_info"]["region"]["long_min"],
                    "lon_max": mesh_json["config"]["mesh_info"]["region"]["long_max"],
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Mesh inserted: name: {mesh.name} \nmd5: {mesh.md5} \
                            \nid: {mesh.id} \
                            \ncreated: {mesh.created} \
                            \nlat: {mesh.lat_min}:{mesh.lat_max}\
                            \nlon: {mesh.lon_min}:{mesh.lon_max}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Mesh with md5: {mesh.md5} already in database. No new records created."
                    )
                )
