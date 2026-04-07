# Development

Depends on:

* Python >=3.11
* [docker](https://docs.docker.com/get-docker/) for running rabbitmq
* [Make](https://www.gnu.org/software/make/)

<br>

1. Clone the repository and create and activate a python virtual environment of your choice.
1. Inside a virtual environment or machine: `pip install -e .[dev]`
1. Make sure you have a running instance of the database, by running `docker compose up`, if it is not running already.
1. Before first use, create the database by running `make migrate`
1. To start all of the services needed for the dev deployment run: `make serve-dev` (which sets the `DJANGO_SETTINGS_MODULE` environment variable and spins up celery, rabbitmq in a docker container, and the Django development server)

For development, also install and use the development tools with `pre-commit install`

The pre-commit hooks include automatic API schema generation. When you commit changes to `polarrouteserver/route_api/views.py`, the API schema (`docs/apischema.yml`) will be automatically updated and included in your commit.

A number of helpful development tools are made available through the `Makefile`, to see a description of each of these commands, run `make` (with no arguments) from the top-level of this directory.

**Important**: Please ensure all changes are included in `CHANGELOG.md` in a human-friendly format.

## Release/Versioning

Version numbers should be used in tagging commits on the `main` branch and reflected in the `pyproject.toml` file and should be of the form `v0.1.7` using the semantic versioning convention.

**Note on version numbers**: Setuptools-scm requires version numbers that begin with a `v` and setuptools requires [PEP 440-compliant version numbers](https://peps.python.org/pep-0440/), e.g. `v0.1.7`, or for non release versions: `v0.1.7a1` for alphas, `v0.1.7rc1` for release candidates. Installing the package will fail if tags have version numbers deviating from this format.

Release preparation (i.e. updating version numbers in `CHANGELOG.md` and `apischema.yml`) can be done automatically with `make prep-release version=<VERSION-NUMBER>` (without the 'v'). Note that this does not rebuild the API schema, just changes the version number.

## Building & deploying the documentation

The documentation should build automatically on pushes to `main` using GitHub actions, if you want to build and deploy the docs manually, follow these steps:

* Run `make build-docs` to build the docs to the `./site` directory.
* Then run `make deploy-docs` to deploy to the `gh-pages` branch of the repository. You must have write access to the repo.

## Making changes to the API

The API is documented in `./docs/apischema.yml` using the OpenAPI 3.0 standard (formerly known as swagger).

If you have pre-commit hooks installed (`pre-commit install`), the API schema will be automatically updated when you commit changes to Python files. The updated schema will be included in your commit.

You can also manually re-generate the schema by running:

```shell
make build-apischema
# or directly:
python manage.py spectacular --color --validate --file docs/apischema.yml
```

Aim to resolve any warnings/errors before committing.

The generated schema can be checked by building the docs and checking the [API reference page](api.md) or serving using swagger (`make start-swagger`).

## Error codes and response schemas
Standard error codes and responses are defined in the `ResponseMixin` class in `responses.py`. Where possible, try to align standard responses (e.g. 200 SUCCESS, 202 ACCEPTED, 400 BAD REQUESTS, 404 NOT FOUND) to these standard codes and responses.

Views in `views.py` can inherit `ResponseMixin` class to make use of these standard responses.

## Docker containers and compose configuration
PolarRoute-server relies on four different services, orchestrated by [docker compose](https://docs.docker.com/compose/install/), to each be running in their own docker container.

As a user, you run a single `docker compose up` command to build and start these services.

As a developer, it is useful to be aware of what exactly these containers are doing.

Pre-fixed by `polarroute-server-`, the four services/containers are:
* `db-*`: a PostgreSQL database.
* `rabbitmq-*`: RabbitMQ.
* `celery-*`: Celery.
* `app-*`: The Django server running PolarRoute-server's route API.

Certain actions may rely on just a single service to be running, for example `make migrate` requires `polarroute-server-db-1` to be running. However, in practice, you will always be running all four containers at the same time.

Configurations for `docker compose up`'s execution are set in `compose.yml`.
