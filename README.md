# PolarRoute-Server

![Dev Status](https://img.shields.io/badge/Status-Active-green)
[![Static Badge](https://img.shields.io/badge/GitHub_repo-black?logo=github)](https://github.com/bas-logist/PolarRoute-server)
[![Documentation](https://img.shields.io/badge/Documentation-blue)](https://bas-logist.github.io/PolarRoute-server/)
[![GitHub Tag](https://img.shields.io/github/v/tag/bas-logist/PolarRoute-server?filter=v*.*.*&label=latest%20release)](https://github.com/bas-logist/PolarRoute-server/tags)
[![GitHub License](https://img.shields.io/github/license/bas-logist/PolarRoute-server)](https://github.com/bas-logist/PolarRoute-server/blob/main/LICENSE)
[![Test Status](https://img.shields.io/github/actions/workflow/status/bas-logist/polarroute-server/tests.yml?branch=main&event=push&label=tests)](https://github.com/bas-logist/PolarRoute-server/actions/workflows/tests.yml)

A web server to manage requests for meshes and routes generated using the [PolarRoute](https://github.com/bas-logist/PolarRoute) and [MeshiPhi](https://github.com/bas-logist/MeshiPhi/) libraries,
implemented using [Django](https://www.djangoproject.com/), [Celery](https://docs.celeryq.dev/) and [Django REST framework](https://www.django-rest-framework.org/).

It currently takes *vessel* meshes created using MeshiPhi or [PolarRoute-pipeline](https://github.com/bas-logist/PolarRoute-pipeline) and serves requests for routes, which are calculated using PolarRoute.

## Setup/installation

PolarRouteServer can be installed from GitHub using `pip`.

+ Inside a virtual environment (e.g. venv, conda, etc.) run `pip install git+https://github.com/bas-logist/PolarRoute-server`
  + To install a specific version append the tag, e.g. `pip install git+https://github.com/bas-logist/PolarRoute-server@v0.1.6`
  + Alternatively, clone this repository with git and install from source with `pip install -e .`

## Quickstart using docker compose (recommended)

Use [docker compose](https://docs.docker.com/compose/install/) for development deployment to orchestrate celery and rabbitmq alongside the django development server.

Clone this repository and run `docker compose up` to build and start the services.

**Note**: In development, meshes are not automatically ingested into the database. Follow these steps to add a mesh to the database.

- Make a local directory structure with `mkdir -p data/mesh` (if it has not been created by `docker compose`).
- If you have a vessel mesh file from MeshiPhi or PolarRoute-pipeline, copy it into `./data/mesh`, which is bind-mounted into the app container. Alternatively, download an example mesh using 

```sh

pushd data/mesh

wget http://files.bas.ac.uk/twins/polarroute/example_vehicle_meshes/amsr_southern_SDA.json.gz && \
wget http://files.bas.ac.uk/twins/polarroute/example_vehicle_meshes/amsr_central_SDA.json.gz && \
wget http://files.bas.ac.uk/twins/polarroute/example_vehicle_meshes/amsr_northern_SDA.json.gz

gunzip amsr_*_SDA.json.gz

popd

```

- Run `docker compose exec app /bin/bash` to open a shell inside the running app container.
- Run `django-admin insert_mesh /usr/src/app/data/mesh/<MESH FILENAME>` to insert the mesh into the database manually.

Test that the app is working using the `request_route` tool (see [Documentation](https://bas-logist.github.io/PolarRoute-server/requesting-routes/#using-the-in-built-route-request-utility-simplest)). The URL of the service should be `localhost:8000`.

The django development server supports hot reloading and the source code is bind-mounted into the container, so changes should be reflected in the running app. Any changes to `polarrouteserver.route_api.models.py` will necessitate a migration to the database. To create and run migrations, run:

```
docker compose exec app django-admin makemigrations
docker compose exec app django-admin migrate
```

Optionally, Swagger can be used to serve an API schema. This is not started by default, but can be enabled by started `docker compose` with the `--profile swagger` option, e.g. `docker compose --profile swagger up -d` - the swagger UI will be served at `localhost:80/swagger`.
