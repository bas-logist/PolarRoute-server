# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `EnvironmentMesh` and `VehicleMesh`, so that routes can be requested for a specific vehicle. Both are kinds of `Mesh` and share its table and ids, so a mesh id identifies the same mesh everywhere. A `VehicleMesh` is an environment mesh with the performance of one vehicle added. At most one exists per environment mesh and vehicle.
- Routes record their `Vehicle` and the `VehicleMesh` they were calculated on (`vehicle_mesh`). The vehicle is returned in the route response.
- `create_and_calculate_route()` task, replacing the `optimise_route()` task. It finds or builds the `VehicleMesh` for the vehicle of the route from the mesh of the route, using PolarRoute's `VesselPerformanceModeller`, then calculates the route.
- Battery-powered vehicles (for example `Slocum`, `BoatyMcBoatFace`): routes are optimised for traveltime and for `battery` or `fuel` use, whichever the vehicle mesh models.
- A route's `info` warns when sea cells of the mesh have no sea ice concentration data, which PolarRoute treats as ice-free.
- `Vehicle` fixtures for `SDA`, `Slocum` and `BoatyMcBoatFace`, added by the new `load_vehicle_fixtures` command when the docker container starts. Vehicles which exist already are not changed. Fixture vehicles can't be deleted through the API.
- Automatic mesh import (`import_new_meshes`) now also imports environment meshes: any `.json` file in the upload metadata that is a mesh.

### Changed
- **Breaking:** `vehicle_type` is required when requesting a route (`request_route.py` takes `-v/--vehicle`) and when evaluating a route. Requests without it are rejected with a 400, and with an unknown vehicle type a 404.
- **Breaking:** in the route response, the type of the energy optimised route is now `energy` (previously `fuel`) and its metric is `energyConsumption`, with a `source` of `fuel` or `battery` (previously `fuelConsumption`).
- `Mesh` rows which exist before upgrading are vessel meshes. The migration makes each of them a `VehicleMesh` with the same id, creating its `Vehicle` from the mesh's `vessel_info` if needed, and sets the vehicle and vehicle mesh of the routes calculated on it.
- `select_mesh()` returns environment meshes, and imported vehicle meshes of the requested vehicle which have no environment mesh, with the imported vehicle mesh first where meshes are the same size. `route_exists()` only finds routes calculated for the same vehicle.
- Mesh ingestion (`insert_mesh` and automatic import) works out the mesh type from the content: with `vessel_info` in its config it is a `VehicleMesh` (and its `Vehicle` is created if it doesn't exist), otherwise an `EnvironmentMesh`.
- Automatic mesh import skips a mesh it can't read or ingest (for example a file which is still transferring) and carries on with the rest.
- Mesh checksums for `insert_mesh` are now calculated in the same way as for automatic import, so a mesh inserted manually which was inserted by an earlier version will be added again.
- A vehicle can't be deleted while vehicle meshes ingested for it exist. Vehicle meshes built for it are deleted with it.
- Cleaning up an environment mesh (`cleanup_meshes`) also deletes the vehicle meshes built from it, unless one of them is protected.
- `optimise_route()` is now a function (not a task) which optimises for traveltime and for the energy use modelled by the vehicle mesh.
- The `polar-route` dependency is now pinned to `==1.2.0` (previously `==1.0.0`). This is the first release in which `route_calc` accepts a route geojson.
- Updated `evaluate_route` to pass the route geojson directly to `route_calc`, removing the manual DataFrame construction and temporary file handling.
- Replaced the GDAL system packages in the Docker image with `libexpat1` (needed by `rasterio`); `polar-route` 1.2.0 no longer depends on Fiona, and the Python geospatial wheels bundle GDAL.

### Fixed
- Disabled celery features which are deprecated by rabbitmq >= 4.3.
- `evaluate_route` now passes `route_type="smoothed"` to `route_calc`, which `polar-route` 1.2.0 requires to be set.
- Updating the properties of a vehicle (`force_properties`) deletes the vehicle meshes built for it, so they are rebuilt with the new properties.
- Route evaluation selected meshes with the latitudes and longitudes of the route swapped.

### Reverted
- Downgraded Django back to 5.2 to account for lack of Django 6.1 support in django-celery-beat.

### Added
- Celery beat service to docker compose configs.
- Testing for celery beat.

## 0.3.0 - 2026-10-26

### Upgraded
- Django 5.2 to Django 6.1

### Removed
- Support for Python < 3.12

### Added
- `/health/` endpoint and `HEALTHCHECK` in the Docker container. 
- Docker production and development settings modules.
- `compose.prod.yml` for modifying the compose config for production.

### Changed
- Re-worked docker container to create a production build-stage.
- Added static file collection to the docker entrypoint script.
- A number of syntax changes throughout to comply with default rules enabled in ruff >0.16.
- Changed calls to `datetime.timezone.utc` to `datetime.UTC`.
 
## 0.2.7 - 2025-12-22

### Added
- Added all ports on localhost, 127.0.0.1 and 0.0.0.0 to CORS allowed origins.

### Changed
- Altered the `/api/recent_routes` endpoint to return routes from the last 24 hours. Previously it returned routes from the current calendar day.
- Renamed and repositioned "Falklands" location to "Mare Harbour".

## 0.2.6 - 2025-12-17

### Fixed
- Added missing migration.


## 0.2.5 - 2025-12-15

### Added
- added ensure_adminuser command to add subtly more sophisticated behaviour to Django's createsuperuser - i.e. don't raise non-zero exit code if superuser already exists, add more useful output.
- Empty arrays to empty responses for a consistent response structure.
- Adding a "tags" field to the Route model. As an optional parameter, tags can be assigned to routes using a POST api/route request. This is implemented using [django-taggit](https://django-taggit.readthedocs.io/en/latest).
- Added environment variables for controlling logging behaviour: POLARROUTE_LOG_FILE_NAME, CELERY_LOG_DIR, CELERY_LOG_FILE_NAME (in addition to existing: POLARROUTE_LOG_DIR).
- Added rotating logging handler.

### Improved
- Improved speed of route changelist admin page.
- Write logs with group-write permissions.
- Use uv in the docker image.

### Changed
- Inappropriate use of 204 code: RecentRoutesView changed from 204 to 200 OK with an empty array and the original message ("No recent routes found for today.").
- Inappropriate use of 204 code: VehicleTypeListView changed from 204 to 200 OK with and empty array and the original message.
- MeshView - Changed from 204 to 404 Not Found when mesh doesn't exist.
- Updated tests to reflect corrected HTTP status codes.
- Remove one layer of error response nesting in failed job response.
- Made route admin panel more read-only and faster; hide full view of JSON fields.

### Fixed
- Corrected mesh data source checking and improved warning message to reduce confusion for missing current data.
- Add erroneously missing `rest_framework` into `INSTALLED_APPS`.
- Remove unique constraint and add id field to locations fixture to prevent duplication.
- Corrected mesh metadata filename pattern.
- Corrected mesh id type in api schema.
- Catch more errors in route evaluation, return a better error message from evaluate route endpoint.




## 0.2.4 - 2025-11-11

### Fixed
- Included migration for changes to location model.
- Inclusion of fixtures in source code distribution by using `MANIFEST.in` in place of `package_data` in `pyproject.toml`.

## 0.2.3 - 2025-11-10

### Added
- This changelog!

### Changed
- Restricted upper limit of Django support to version 5.2
- Name of maintainer from David Wilby to David Wyld.
- Moved the docker volume for the `db` service to a managed volume instead of a bind-mount.

#### `request_route`
- utility move to its own module.

### Fixed
- `request_route` utility now does not wait for the delay period before the first status request, only after receipt of a 'PENDING' job status.

### Removed
- Support for python 3.9
- Support for Django < 5.2


## 0.2.2 - 2025-10-14

### Added
- Optimisation metrics exposure (time, fuel, distance) in route responses.
- Job ID inclusion in `recent_routes` response for better tracking.
- Recent routes output validation tests.

### Changed
- **Breaking**: Route response structure now consistent regardless of optimisation types available.
- Improved `recent_routes` endpoint performance by removing repeated job status calls and heavy JSON processing.
- Route calculated timestamp only applied when both route optimisations are complete.
- Re-coupled `recent_routes` status to Celery state using database instead of broker for better reliability/performance.
- Removed top-level metadata duplication in route responses.

### Fixed
- Performance issues with `recent_routes` endpoint loading unnecessary data.

## 0.2.1 - 2025-09-18

### Added
- Response refactor for improved error code consistency.
- New `responses.py` module for centralized response handling.
- Response validation tests (`test_responses.py`).
- Location management functionality.
- Job status schema with all possible Celery states.
- Vehicle management with CRUD operations.
- Vehicle configuration validation using PolarRoute validator.
- Location fixtures for standard locations (Bird Island, Falklands, Halley, Rothera, etc.).
- Swagger UI served alongside the application.

### Changed
- **Breaking**: Separated job and route endpoints - routes now accessed via job workflow.
- **Breaking**: Route cancellation moved from route endpoint to job endpoint.
- Unified error responses across all endpoints for consistency.
- Route model now cascades deletion when job is deleted.
- Vehicle model expanded with additional SDA properties (`beam`, `hull_type`, `force_limit`).
- LocationView refactored to `LocationViewSet`.

### Fixed
- Route schema missing from API documentation after merge conflicts.
- Inconsistent error response formats across endpoints.
- Route cancellation bug where deletion didn't work properly.

### Removed
- Redundant "no mesh available" response variations - now unified.
- Separate route cancellation endpoint (moved to job endpoint).

## 0.2.0 - 2025-02-19

## 0.1.6 - 2024-12-09

## 0.1.5 - 2024-12-05

## 0.1.4 - 2024-11-28

## 0.1.3 - 2024-11-26

## 0.1.2 - 2024-11-25

## 0.1.1 - 2024-11-20

## 0.1.0 - 2024-11-20

