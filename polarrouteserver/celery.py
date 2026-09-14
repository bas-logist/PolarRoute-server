import logging
import os

from celery import Celery, signals
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "polarrouteserver.settings.production")

app = Celery("polarrouteserver")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


@signals.setup_logging.connect
def on_celery_setup_logging(**kwargs):
    config = settings.CELERY_LOGGING

    logging.config.dictConfig(config)
