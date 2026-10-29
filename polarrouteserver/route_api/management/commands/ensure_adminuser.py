import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates an admin user non-interactively if it doesn't exist"

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Admin's username")
        parser.add_argument("--email", help="Admin's email")
        parser.add_argument("--password", help="Admin's password")
        parser.add_argument(
            "--no-input", help="Read options from the environment", action="store_true"
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if options["no_input"]:
            options["username"] = os.environ.get("POLARROUTE_SUPERUSER_USERNAME")
            options["email"] = os.environ.get("POLARROUTE_SUPERUSER_EMAIL")
            options["password"] = os.environ.get("POLARROUTE_SUPERUSER_PASSWORD")

        if not User.objects.filter(username=options["username"]).exists():
            user = User.objects.create_superuser(
                username=options["username"],
                email=options["email"],
                password=options["password"],
            )
            if user:
                self.stdout.write(self.style.SUCCESS(f"Created superuser: {user}"))
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to create superuser: {options['username']}"
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Superuser: {options['username']} not created. Already exists."
                )
            )
