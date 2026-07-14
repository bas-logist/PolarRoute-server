# How PolarRoute-server works

This page gives an overview of the architecture and approach of the software for developers or administrators of PolarRoute-server.

## PolarRoute-server architecture

As with all Django apps, PolarRoute-server follows a model-view-controller-like architecture ([see Django FAQ for the specifics](https://docs.djangoproject.com/en/5.1/faq/general/#django-appears-to-be-a-mvc-framework-but-you-call-the-controller-the-view-and-the-view-the-template-how-come-you-don-t-use-the-standard-names)) in which a `models.py` file defines the tables in the database; `views.py` defines the handling of HTTP requests. Most Django apps also have templates, but since PolarRoute-server is headless, we don't need these.

The route request workflow is separated into distinct endpoints:

1. **Route Request Submission**: User submits a route request via POST to the `/api/route` endpoint.
1. **Job Creation**: A celery job is created for route calculation (defined in `tasks.py`) and the client receives a job ID and status URL.
1. **Job Status Monitoring**: Client polls the `/api/job/{job_id}` endpoint by GET request to monitor calculation progress.
1. **Route Data Retrieval**: Once the job is complete, client retrieves the route data from `/api/route/{route_id}` endpoint.

In short:

- **`POST /api/route`**: Submit route calculation request → returns job ID.
- **`GET /api/job/{job_id}`**: Monitor job status and progress.
- **`DELETE /api/job/{job_id}`**: Cancel running job.
- **`GET /api/route/{route_id}`**: Retrieve calculated route data.

To calculate a route, PolarRoute requires a mesh that covers the area of the start and end points of the route.

## Ingesting meshes into the database

For the time-being, meshes are calculated separately to PolarRoute-server, either with PolarRoute-pipeline or with MeshiPhi directly.

PolarRoute-server ingests two types of meshes:

- **Environment Meshes**: Environmental data.
- **Vehicle Meshes**: Environmental data + vessel performance information.

PolarRoute-server automatically detects which type of mesh is being ingested (based on the presence/absence of vehicle information) and creates the appropriate database records.

### How It Works

1. **Detects mesh type**: Looks for `vessel_info` in the mesh config
   - Has `vessel_info` → **Vehicle Mesh**
   - No `vessel_info` → **Environment Mesh**

2. **Creates database records**: 
   - Vehicle meshes also create Vehicle records automatically
   - Uses MD5 hash to avoid duplicates

3. **Cleans data**: Fixes common issues like `null` values in ice data

Meshes can be ingested into the database manually or automatically.

By default, development deployments (using the `polarrouteserver/settings/development.py` settings) perform no automatic mesh ingestion, and production deployments (using the `polarrouteserver/settings/production.py` settings) use celery-beat to perform automatic ingestion of meshes every 10 minutes, running the `import_new_meshes` task (`polarrouteserver/route_api/tasks.py`).

### Automatically

Meshes are found automatically in the directories specified using the `POLARROUTE_MESH_DIR` & `POLARROUTE_MESH_METADATA_DIR` environment variables (see [Configuration](configuration.md) for specific behaviour). Mesh metadata files produced by PolarRoute-pipeline are used to validate newly available meshes, only meshes which are not already in the database (determined using their md5 hash) are ingested. Mesh metadatafiles must be named according to the format `upload_metadata_*.yaml.gz` to be found.

### Manually

Individual or lists of mesh files can be ingested into the database by running the `insert_mesh` command using `django-admin` or `python manage.py`, e.g. `django-admin insert_mesh path/to/my/mesh.vessel.json`.

`insert_mesh` can take `json` files or `json.gz` files.

## Route requests and jobs

When a route is requested, the `select_mesh` function is called to determine which mesh to use (described below in [Mesh selection](#mesh-selection)) unless a specific mesh id is requested in the route request.

The `route_exists` function is called for the start and end points and the mesh selected, if there is already an existing route which was successful, this is returned unless the client specifies `force_new_route: true`, in which case the route is recalculated. Whether a route is considered to "exist" or not depends on a tolerance in the haversine distance of the requested start and end locations compared to routes which have already been calculated. This distance by default is 1 nautical mile (set by the `WAYPOINT_DISTANCE_TOLERANCE` setting). In other words, if a route is requested where the requested start point is within 1NM of a route already calculated and the same is true of the end point, this route is returned under default conditions. Note that if a newer mesh is available, a new route will be calculated.

Because route optimisation jobs can take several minutes, this is done by an asynchronous job queue managed by celery.

If the route optimisation fails, the next mesh in priority order is tried if the failure is due to the route being "inaccessible" on the mesh.

## Mesh selection
Before a route is calculated, a priority list of meshes is created by `polarrouteserver.route_api.utils.select_mesh`.

It takes all of the meshes that contain the requested start and end coordinates and that were created on the latest date available out of those meshes and returns this list of meshes sorted from smallest to largest total area.

The system will initially look for a `VehicleMesh` for the requested vehicle type. If not found, it will attempt to create one from an `EnvironmentMesh` and the vehicle type provided. It will then use the created VehicleMesh for route optimisation. 

## Troubleshooting