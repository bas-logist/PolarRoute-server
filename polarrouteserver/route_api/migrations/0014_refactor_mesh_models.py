# Custom migration for mesh refactoring

import django.db.models.deletion
from django.db import migrations, models


def migrate_mesh_data(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        # Check if there's any data to migrate
        cursor.execute(
            "SELECT id, meshiphi_version, md5, valid_date_start, valid_date_end, created, lat_min, lat_max, lon_min, lon_max, json, name FROM route_api_mesh"
        )
        mesh_data = cursor.fetchall()

        # Create VehicleMesh records for each existing Mesh
        for row in mesh_data:
            (
                mesh_id,
                meshiphi_version,
                md5,
                valid_date_start,
                valid_date_end,
                created,
                lat_min,
                lat_max,
                lon_min,
                lon_max,
                json_data,
                name,
            ) = row

            # Insert into VehicleMesh table
            cursor.execute(
                """
                INSERT INTO route_api_vehiclemesh 
                (meshiphi_version, md5, valid_date_start, valid_date_end, created, lat_min, lat_max, lon_min, lon_max, json, name, environment_mesh_id, vehicle_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                [
                    meshiphi_version,
                    md5,
                    valid_date_start,
                    valid_date_end,
                    created,
                    lat_min,
                    lat_max,
                    lon_min,
                    lon_max,
                    json_data,
                    name,
                    mesh_id,
                    None,
                ],
            )

            # Get the ID of the newly created VehicleMesh
            cursor.execute("SELECT lastval()")
            vehicle_mesh_id = cursor.fetchone()[0]

            # Update Route references to point to the new VehicleMesh
            cursor.execute(
                "UPDATE route_api_route SET mesh_id = %s WHERE mesh_id = %s",
                [vehicle_mesh_id, mesh_id],
            )


def reverse_migrate_mesh_data(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DELETE FROM route_api_vehiclemesh")


class Migration(migrations.Migration):
    dependencies = [
        ("route_api", "0013_location"),
    ]

    operations = [
        # Create VehicleMesh table
        migrations.CreateModel(
            name="VehicleMesh",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("meshiphi_version", models.CharField(max_length=60, null=True)),
                ("md5", models.CharField(max_length=64)),
                ("valid_date_start", models.DateField()),
                ("valid_date_end", models.DateField()),
                ("created", models.DateTimeField()),
                ("lat_min", models.FloatField()),
                ("lat_max", models.FloatField()),
                ("lon_min", models.FloatField()),
                ("lon_max", models.FloatField()),
                ("json", models.JSONField(null=True)),
                ("name", models.CharField(max_length=150, null=True)),
                (
                    "environment_mesh",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="route_api.mesh",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="route_api.vehicle",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Vehicle Meshes",
            },
        ),
        # Migrate data from Mesh to VehicleMesh and update Route references
        migrations.RunPython(
            migrate_mesh_data,
            reverse_migrate_mesh_data,
        ),
        # Update Route.mesh to point to VehicleMesh
        migrations.AlterField(
            model_name="route",
            name="mesh",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="route_api.vehiclemesh",
            ),
        ),
        # Rename Mesh to EnvironmentMesh
        migrations.RenameModel(
            old_name="Mesh",
            new_name="EnvironmentMesh",
        ),
        # Set correct Meta options for EnvironmentMesh
        migrations.AlterModelOptions(
            name="environmentmesh",
            options={"verbose_name_plural": "Environment Meshes"},
        ),
        # Update VehicleMesh.environment_mesh to point to EnvironmentMesh
        migrations.AlterField(
            model_name="vehiclemesh",
            name="environment_mesh",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="route_api.environmentmesh",
            ),
        ),
    ]
