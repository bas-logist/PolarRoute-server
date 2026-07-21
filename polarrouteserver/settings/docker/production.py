from polarrouteserver.settings.production import *

logger = logging.getLogger(__name__)

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
