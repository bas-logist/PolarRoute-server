# Configuration

Configuration of PolarRouteServer works with environment variables. You can either set these directly or from a `.env` file. An example `.env` file is included in the repo as `env.example`.

Environment variables used directly by the Django site are prefixed wit `POLARROUTE_` and those which configure Celery are prefixed with `CELERY_`.

## Mesh settings

- `POLARROUTE_MESH_DIR` - absolute path to directory where mesh files will be made available (this location is periodically checked in production and new files ingested into the database based on the metadata file). A warning is logged in production if this is not set.
- `POLARROUTE_MESH_METADATA_DIR` - as above, absolute path to directory where mesh metadata files will be made available. If this is not set, the value of `POLARROUTE_MESH_DIR` is used and a warning to this effect is logged.

## Django settings

The following are inherited from Django and more information can be found on their effects via the [Django docs](https://docs.djangoproject.com/en/5.1/ref/settings/).

- `POLARROUTE_DEBUG` - enables Django debug options, must be `False` in production (default: `False`)
- `POLARROUTE_SECRET_KEY` - secret hash used for cookie signing etc. Must be set in production. A random key is generated if one is not set.
- `DJANGO_SETTINGS_MODULE` - sets the settings envrionment. Options: `polarrouteserver.settings.{production,development,test}` (Default: `polarrroutesserver.settings.production`)
- `POLARROUTE_ALLOWED_HOSTS` - comma-separated (no spaces) list of IP addresses or hostnames allowed for the server.
- `POLARROUTE_CORS_ALLOWED_ORIGINS` -  comma-separated (no spaces) list of IP addresses allowed for Cross Origin Site Requests. (See [django-cors-headers](https://pypi.org/project/django-cors-headers/) on PyPI for more.)
- `CELERY_BROKER_URL` - URL for rabbitMQ message broker used by celery. (Default: `amqp://guest:guest@localhost`)
- `POLARROUTE_LOG_LEVEL` - sets the logging level from standard log level options: INFO, DEBUG, ERROR, WARNING etc. (Default: `INFO`)
- `POLARROUTE_LOG_DIR` - sets the output directory for logs. By default only used in production settings environment.
- `POLARROUTE_STATIC_ROOT` - the path to directory used for static file serving in production, e.g. `"/var/www/example.com/static/"` (Default: `None`) Note this is only used for the admin panel in this application.
- Automated database cleanup settings, only active for `DJANGO_SETTINGS_MODULE` production values e.g. `polarrouteserver.settings.production`:
  - Route cleanup, runs once per day by default, at 02:00UTC
    - `POLARROUTE_CLEANUP_ROUTES` - set to `True` to enable automated cleanup (delete) process for routes older than `POLARROUTE_CLEANUP_ROUTES_DAYS`. (Default: False)
    - `POLARROUTE_CLEANUP_ROUTES_DAYS` - if `POLARROUTE_CLEANUP_ROUTES` is `True`, routes older than this value are deleted. (Default: 365)
  - Mesh cleanup, runs once per day by default, at 03:00UTC
    - `POLARROUTE_CLEANUP_MESHES` - set to `True` to enable automated cleanup (delete) process for meshes older than `POLARROUTE_CLEANUP_ROUTES_DAYS`. (Default: False)
    - `POLARROUTE_CLEANUP_MESHES_DAYS` - if `POLARROUTE_CLEANUP_ROUTES` is `True`, meshes older than this value are deleted. (Default: 365)

## Database settings

- `POLARROUTE_DB_NAME` - postgres database name (default: `polarroute`)
- `POLARROUTE_DB_USER` - postgres database user (default: `polarroute`)
- `POLARROUTE_DB_PASSWORD` - postgres database password (default: `polarroute`)
- `POLARROUTE_DB_HOST` - postgres database host (default: `127.0.0.1`)
- `POLARROUTE_DB_PORT` - postgres database port (default: `5432`)