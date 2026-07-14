# Vehicle Management

In order to add vehicles to environment meshes, they will first need to be created in the database.

For details on the API, see the [API reference page](api.md).

## Creating vehicles

To request a vehicle to be added to the database, make a POST request to the `/api/vehicle` endpoint,
for example with the following CURL:

```shell
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{
       "vessel_type": "SDA",
       "max_speed": 26.5,
       "unit": "km/hr",
       "beam": 24.0,
       "hull_type": "slender",
       "force_limit": 96634.5,
       "max_ice_conc": 80,
       "min_depth": 10 
    }' \
  http://localhost:8000/api/vehicle
```

This will create a vehicle of `vessel_type` "SDA" in the database. Note that `vessel_type` is unique,
and any subsequent request to create the same vessel type will result in an error.

## Updating vehicle properties

Should you wish to update a `vessel_type`'s properties after creation, you can do so using the
`force_properties` argument in your request.

Let's say we actually wanted to display the speed in knots:

```shell
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{
      "vessel_type": "SDA",
      "max_speed": 14.3,
      "unit": "knots",
      "beam": 24.0,
      "hull_type": "slender",
      "force_limit": 96634.5,
      "max_ice_conc": 80,
      "min_depth": 10,
      "force_properties":"true"
    }' \
  http://localhost:8000/api/vehicle
```
With `"force_properties"` set to `"true"`, the request will be accepted and the properties for "SDA"
will be updated.

## Requesting a list of all available vehicles
To request a list of all available vehicles in the database, you can make a GET request to the
`api/vehicle/available` endpoint:

```shell
curl --header "Content-Type: application/json" \
  --request GET \
  http://localhost:8000/api/vehicle/available
```

## Requesting vehicles
### Requesting a specific vehicle
To request a specific vehicle to be returned, you can make a GET request to the `api/vehicle`
endpoint, adding the `vessel_type` to the end of the endpoint, for example `api/vehicle/SDA`:

```shell
curl --header "Content-Type: application/json" \
  --request GET \
  http://localhost:8000/api/vehicle/SDA/

```

### Requesting all vehicles
If you make a GET request to `api/vehicle` without specifying the `vessel_type`, all vehicles will
be returned.

```shell
curl --header "Content-Type: application/json" \
  --request GET \
  http://localhost:8000/api/vehicle
```

## Deleting a vehicle
To request a vehicle to be removed from the database, you can make a DELETE request to `api/vehicle`,
specifying the `vessel_type` in the URL, just as with specific vehicle GET requests, `api/vehicle/SDA`:

```shell
curl --header "Content-Type: application/json" \
  --request DELETE \
  http://localhost:8000/api/vehicle/SDA/

```

Removing all vehicles in one go is not currently supported. 

## Adding a vehicle to an environment mesh

Vehicles are added to an `EnvironmentMesh` automatically, creating a `VehicleMesh`, if a route is requested with a vehicle type where a `VehicleMesh` is not already available for those coordinates.

## Creating vehicles with mesh ingestion

Vehicles are also created automatically (if they do not exist already), when a `VehicleMesh` is ingested into the database. This process is described in [mesh ingestion](how-polarroute-server-works.md#ingesting-meshes-into-the-database).