from pathlib import Path

from celery.schedules import crontab

from .base import *

TEST_MESH_PATH = Path("tests", "fixtures", "test_vessel_mesh.json")
TEST_ROUTE_PATH = Path("tests", "fixtures", "test_route.json")
TEST_ROUTE_OOM_PATH = Path("tests", "fixtures", "test_route_out_of_mesh.json")
TEST_VEHICLE_PATH = Path("tests", "fixtures", "test_vessel_config.json")
MESH_DIR = "tests/fixtures"
MESH_METADATA_DIR = MESH_DIR
MESH_METADATA_GLOB_PATTERN = "upload_metadata_*.yaml.gz"

S3_ENDPOINT_URL = "http://localhost:5000"
S3_KEY = "testing"
S3_SECRET = "testing"
S3_REGION = "eu-west-1"

CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "db+sqlite:///results.sqlite"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_TASK_EAGER_PROPAGATES = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}


CELERY_BEAT_SCHEDULE = {
    "my_test_task": {
        "task": "polarrouteserver.route_api.tasks.my_test_task",
        "schedule": crontab(minute="*/1"),
    }
}
