# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
 
 
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

