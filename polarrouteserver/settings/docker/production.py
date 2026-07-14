from celery.schedules import crontab

from polarrouteserver.settings.base import *

logger = logging.getLogger(__name__)

if MESH_DIR is None:
    pass
    # disabling these warnings in settings modules until we can resolve https://github.com/bas-amop/PolarRoute-server/issues/49
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

# whitenoise for static file serving, needs to be in specific middleware position https://whitenoise.readthedocs.io/en/stable/django.html
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


LOGLEVEL = os.environ.get("POLARROUTE_LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "%(asctime)s%(process)d/%(thread)d%(name)s%(funcName)s %(lineno)s%(levelname)s%(message)s",
            "datefmt": "%Y/%m/%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOGLEVEL,
    },
    "loggers": {
        # Catch all Django-specific logs
        "django": {
            "handlers": ["console"],
            "level": LOGLEVEL,
            "propagate": False,
        },
        # Catch all database queries (only prints if LOGLEVEL is DEBUG)
        "django.db.backends": {
            "handlers": ["console"],
            "level": LOGLEVEL,
            "propagate": False,
        },
    },
}

CELERY_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "%(asctime)s%(process)d/%(thread)d%(name)s%(funcName)s %(lineno)s%(levelname)s%(message)s",
            "datefmt": "%Y/%m/%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOGLEVEL,
    },
    "loggers": {
        "celery": {
            "handlers": ["console"],
            "level": LOGLEVEL,
            "propagate": False,
        },
    },
}

STATIC_ROOT = os.getenv("POLARROUTE_STATIC_ROOT", None)
