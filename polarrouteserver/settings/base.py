"""
Django settings for polarrouteserver project.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

import logging
import os
import secrets

from polarrouteserver._version import __version__ as polarrouteserver_version

logger = logging.getLogger(__name__)

BASE_DIR = os.getenv("POLARROUTE_BASE_DIR", os.getcwd())
MESH_DIR = os.getenv("POLARROUTE_MESH_DIR", None)
MESH_METADATA_DIR = os.getenv("POLARROUTE_MESH_METADATA_DIR", None)

# FIXTURE_DIRS = []

# NOTE: set this in production
SECRET_KEY = os.getenv("POLARROUTE_SECRET_KEY", secrets.token_hex(100))
DEBUG = os.getenv("POLARROUTE_DEBUG", "False").lower() == "True"

ALLOWED_HOSTS = [
    "localhost",
    "0.0.0.0",
    "127.0.0.1",
]
if os.getenv("POLARROUTE_ALLOWED_HOSTS", None) is not None:
    ALLOWED_HOSTS.extend(os.getenv("POLARROUTE_ALLOWED_HOSTS").split(","))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
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
    },
    "loggers": {
        "root": {
            "handlers": ["console"],
            "level": os.getenv("POLARROUTE_LOG_LEVEL", "INFO"),
            "propagate": True,
        },
    },
}

CELERY_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
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
    },
    "loggers": {
        "celery": {"handlers": ["celery"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "DEBUG"},
}

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_results",
    "django_celery_beat",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "taggit",
    "polarrouteserver.route_api",
    "corsheaders",
]

CORS_ALLOWED_ORIGINS = []
if os.getenv("POLARROUTE_CORS_ALLOWED_ORIGINS", None) is not None:
    CORS_ALLOWED_ORIGINS.extend(os.getenv("POLARROUTE_CORS_ALLOWED_ORIGINS").split(","))

# Allow all localhost origins for CORS in development
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^(?:https*:\/\/)*localhost:\d{2,4}$",  # matches localhost with or without http(s):// and a port of 2-4 digits
    r"^(?:https*:\/\/)*127.0.0.1:\d{2,4}$",  # same for 127.0.0.1
    r"^(?:https*:\/\/)*0.0.0.0:\d{2,4}$",  # same for 0.0.0.0
]

CORS_ALLOW_METHODS = ("DELETE", "GET", "POST", "OPTIONS")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PolarRoute-Server",
    "DESCRIPTION": "Backend server for serving PolarRoute and MeshiPhi assets",
    "VERSION": polarrouteserver_version,
    "SERVE_INCLUDE_SCHEMA": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SECURITY": [],
    "AUTHENTICATION_WHITELIST": [],
}

TAGGIT_CASE_INSENSITIVE = True

ROOT_URLCONF = "polarrouteserver.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "polarrouteserver.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POLARROUTE_DB_NAME", "polarroute"),
        "USER": os.getenv("POLARROUTE_DB_USER", "polarroute"),
        "PASSWORD": os.getenv("POLARROUTE_DB_PASSWORD", "polarroute"),
        "HOST": os.getenv("POLARROUTE_DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("POLARROUTE_DB_PORT", 5432),
    }
}

# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery settings
CELERY_WORKER_HIJACK_ROOT_LOGGER = True
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "django-db")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"


# Routing settings (TODO: hardcoded, can / should these be exposed elsewhere?)
WAYPOINT_DISTANCE_TOLERANCE = 1  # Nautical Miles

# For now, vessel config is used in the pipeline to calculate a vessel mesh
# VESSEL_CONFIG =  {
#        "vessel_type": "SDA",
#        "max_speed": 30,
#        "unit": "km/hr",
#        "beam": 10,
#        "hull_type": "slender",
#        "force_limit": 100000,
#        "max_ice_conc": 80,
#        "min_depth": 10
# }
base_routeplanner_config = {
    "path_variables": ["fuel", "traveltime"],
    "vector_names": ["uC", "vC"],
    "zero_currents": False,
    "variable_speed": True,
    "time_unit": "days",
    "early_stopping_criterion": True,
    "save_dijkstra_graphs": True,
    "waypoint_splitting": False,  # switched off until github.com/bas-amop/polarroute/issues#303 is resolved
    "smooth_path": {"max_iteration_number": 1000, "minimum_difference": 0.0005},
    "smoothing_max_iterations": 100,
    "smoothing_merge_separation": 1e-3,
    "smoothing_converged_sep": 1e-3,
}
TRAVELTIME_CONFIG = base_routeplanner_config | {"objective_function": "traveltime"}
FUEL_CONFIG = base_routeplanner_config | {"objective_function": "fuel"}

# dictionary relating user-friendly name of data source with loader value used in vessel mesh json
EXPECTED_MESH_DATA_SOURCES = {
    "bathymetry": "GEBCO",
    "current": "duacs_currents",
    "sea ice concentration": "amsr",
    "thickness": "thickness",
    "density": "density",
}

# number of data files expected in data_sources.params.files related by loader name as above
EXPECTED_MESH_DATA_FILES = {
    "GEBCO": 1,
    "duacs_current": 3,
    "amsr": 3,
    "thickness": 0,
    "density": 0,
}
