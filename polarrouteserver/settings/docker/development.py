from celery.schedules import crontab

from polarrouteserver.settings.base import *
from polarrouteserver.settings.development import *

STATIC_ROOT = os.getenv("POLARROUTE_STATIC_ROOT", os.path.join(BASE_DIR, "static"))

CELERY_BEAT_SCHEDULE = {}

if MESH_DIR is None:
    pass
    # disabling these warnings in settings modules until we can resolve https://github.com/bas-logist/PolarRoute-server/issues/49
    # logger.warning(
    #     "POLARROUTE_MESH_DIR or POLARROUTE_MESH_METADATA_DIR not set, both are required to ingest new meshes into database.\n\
    #                No new meshes will be automatically ingested."
    # )
else:
    if MESH_METADATA_DIR is None:
        MESH_METADATA_DIR = MESH_DIR
        # logger.warning(
        #     f"POLARROUTE_MESH_METADATA_DIR not set. Using POLARROUTE_MESH_DIR as POLARROUTE_MESH_METADATA_DIR: {MESH_DIR}"
        # )

    CELERY_BEAT_SCHEDULE["import_meshes"] = {
        "task": "polarrouteserver.route_api.tasks.import_new_meshes",
        "schedule": crontab(minute="*/10"),
    }

if CLEANUP_ROUTES:
    CELERY_BEAT_SCHEDULE["cleanup_routes"] = {
        "task": "cleanup_routes",
        "schedule": crontab(minute=0, hour=2),
    }

if CLEANUP_MESHES:
    CELERY_BEAT_SCHEDULE["cleanup_meshes"] = {
        "task": "cleanup_meshes",
        "schedule": crontab(minute=0, hour=3),
    }
