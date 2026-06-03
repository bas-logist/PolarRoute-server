# Requesting Routes

## Using the in-built `request_route` utility (simplest)

A route request script is available in this repo (`./request_route/request_route.py`) to be used as a utility for making route requests.

To obtain, either:

+ Clone this whole repo
+ Download the file from its GitHub page here: https://github.com/bas-logist/PolarRoute-server/blob/main/request_route/route_request.py

This can be done with `wget` by running:

```
wget https://raw.githubusercontent.com/bas-logist/PolarRoute-server/refs/heads/main/request_route/request_route.py
```

To run, you'll just need python ~3.11 installed. Earlier versions of python may work, but are untested.

### Usage
Help for the utility can be printed out by running `python request_route.py --help`.

Alternatively, if you have the package installed, a command named `request_route` is made available.

```sh
$ request_route --help
# OR
$ python request_route.py --help

usage: request_route.py [-h] [-u URL] -s [START] -e [END] [-d [DELAY]] [-n [REQUESTS]] [-m [MESHID]] [-f] [-o [OUTPUT]]

Requests a route from polarRouteServer, monitors job status until complete, then retrieves the route data. Specify start and end points by coordinates or from one of the standard locations: ['bird', 'falklands', 'halley', 'rothera', 'kep', 'signy', 'nyalesund', 'harwich', 'rosyth']

options:
  -h, --help            show this help message and exit
  -u URL, --url URL     Base URL to send request to.
  -s [START], --start [START]
                        Start location either as the name of a standard location or latitude,longitude separated by a comma, e.g. -56.7,-65.01
  -e [END], --end [END]
                        End location either as the name of a standard location or latitude,longitude separated by a comma, e.g. -56.7,-65.01
  -d [DELAY], --delay [DELAY]
                        (integer) number of seconds to delay between status calls. Default: 30
  -n [REQUESTS], --requests [REQUESTS]
                        (integer) number of status requests to make before stopping. Default: 10
  -m [MESHID], --meshid [MESHID]
                        (integer) Custom mesh ID.
  -f, --force           Force polarRouteServer to recalculate the route even if it is already available.
  -o [OUTPUT], --output [OUTPUT]
                        File path to write out route to. (Default: None and print to stdout)
```

So to request a route from Falklands to Rothera, for example:

```sh
python request_route.py --url http://example-polar-route-server.com -s falklands -e rothera --delay 120 --output demo_output.json
```

This will request the route from the server running at `http://example-polar-route-server.com`, and initiate a route calculation if one is not already available.

The utility will then monitor the job status every `120` seconds until the route calculation is complete.

The HTTP response from each request will be printed to stdout.

Once the route is available it will be retrieved and returned, or if the maximum number of attempts have passed, the utility will stop.

## By making HTTP requests

For details on the API, see the [API reference page](api.md).

The route request workflow consists of three steps:

### 1. Submit Route Request

Make a POST request to the `/api/route` endpoint to submit a route calculation job:

```bash
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{"start_lat":"-51.73","start_lon":"-57.71", "end_lat":"-54.03","end_lon":"-38.04"}' \
  http://localhost:8000/api/route
```

This will return a response containing:

- `id`: The job ID for monitoring status.
- `status-url`: URL for checking job status (e.g., `http://localhost:8000/api/job/{job_id}`).
- If a pre-existing route is found, it may be returned immediately.

### 2. Monitor Job Status

Use the job ID to monitor the calculation status by making GET requests to the `/api/job/{job_id}` endpoint:

```bash
curl --header "Content-Type: application/json" \
  --request GET \
  http://localhost:8000/api/job/5c39308e-b88c-4988-9e4b-1c33bc97c90c
```

The response will include:

- `status`: Current job status. Possible values (these are [Celery states](https://docs.celeryq.dev/en/latest/reference/celery.states.html)):

    - `PENDING`: Task is waiting for execution
    - `STARTED`: Task has been started
    - `SUCCESS`: Task executed successfully (route data is ready)
    - `FAILURE`: Task failed with an exception
    - `RETRY`: Task is being retried after failure
    - `REVOKED`: Task was revoked/cancelled

- `route_id`: The route ID for data retrieval (available when status is SUCCESS).
- `route_url`: Direct URL to retrieve the route data (e.g., `http://localhost:8000/api/route/{route_id}`).
- `info`: Error details (only present when status is FAILURE).

### 3. Retrieve Route Data

Once the job status is SUCCESS, retrieve the actual route data using the route ID:

```bash
curl --header "Content-Type: application/json" \
  --request GET \
  http://localhost:8000/api/route/9
```

This will return the complete route data.

### Optional: Cancel Job

You can cancel a running job by making a DELETE request to the job endpoint:

```bash
curl --header "Content-Type: application/json" \
  --request DELETE \
  http://localhost:8000/api/job/5c39308e-b88c-4988-9e4b-1c33bc97c90c
```
