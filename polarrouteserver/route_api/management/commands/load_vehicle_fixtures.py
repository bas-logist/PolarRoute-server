import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from polarrouteserver.route_api.models import Vehicle

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "vehicles.json"


class Command(BaseCommand):
    help = "Add the default vehicles to the database.\n\
            Vehicles which already exist are left unchanged."

    def handle(self, *args, **options):
        with open(FIXTURE_PATH) as f:
            records = json.load(f)

        for record in records:
            fields = dict(record["fields"])
            vehicle, created = Vehicle.objects.get_or_create(
                vessel_type=fields.pop("vessel_type"),
                defaults=fields | {"created": timezone.now()},
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Vehicle added: {vehicle.vessel_type}")
                )
            else:
                self.stdout.write(
                    f"Vehicle {vehicle.vessel_type} already exists, unchanged."
                )
