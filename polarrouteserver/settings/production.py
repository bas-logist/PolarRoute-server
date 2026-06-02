from pathlib import Path
import warnings

from celery.schedules import crontab

from .base import *

logger = logging.getLogger(__name__)

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

    CELERY_BEAT_SCHEDULE = {
        "import_meshes": {
            "task": "polarrouteserver.route_api.tasks.import_new_meshes",
            "schedule": crontab(minute="*/10"),
        },
    }

polarroute_log_file_name = os.getenv("POLARROUTE_LOG_FILE_NAME", "polarrouteserver.log")
polarroute_log_dir = os.getenv("POLARROUTE_LOG_DIR", None)
if polarroute_log_dir is None:
    polarroute_log_dir = Path(BASE_DIR, "logs")
    warnings.warn(
        f"CELERY_LOG_DIR not set. PolarRoute-server logs will be written to: {os.path.join(polarroute_log_dir, polarroute_log_file_name)}"
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {process:d} {module} {levelname} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "level": os.getenv("POLARROUTE_LOG_LEVEL", "INFO"),
            "class": "polarrouteserver.utils.loggers.GroupWriteRotatingFileHandler",
            "maxBytes": 1024 * 1024 * 5,
            "backupCount": 5,
            "filename": os.path.join(
                polarroute_log_dir,
                polarroute_log_file_name,
            ),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "root": {
            "handlers": ["console", "file"],
            "level": os.getenv("POLARROUTE_LOG_LEVEL", "INFO"),
            "propagate": True,
        },
    },
}

celery_log_file_name = os.getenv("CELERY_LOG_FILE_NAME", "celery.log")
celery_log_dir = os.getenv("CELERY_LOG_DIR", None)
if celery_log_dir is None:
    celery_log_dir = Path(BASE_DIR, "logs")
    warnings.warn(
        f"CELERY_LOG_DIR not set. Celery logs will be written to: {os.path.join(celery_log_dir, celery_log_file_name)}"
    )

CELERY_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s%(process)d/%(thread)d%(name)s%(funcName)s %(lineno)s%(levelname)s%(message)s",
            "datefmt": "%Y/%m/%d %H:%M:%S",
        }
    },
    "handlers": {
        "celery": {
            "level": "INFO",
            "class": "polarrouteserver.utils.loggers.GroupWriteRotatingFileHandler",
            "maxBytes": 1024 * 1024 * 5,
            "backupCount": 5,
            "filename": os.path.join(
                celery_log_dir,
                celery_log_file_name,
            ),
            "formatter": "default",
        },
        "default": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "celery": {"handlers": ["celery"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "DEBUG"},
}

STATIC_ROOT = os.getenv("POLARROUTE_STATIC_ROOT", None)
