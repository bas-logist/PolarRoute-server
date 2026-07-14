from django.contrib import admin

from .models import Vehicle, Route, Job, VehicleMesh, EnvironmentMesh, Location

LIST_PER_PAGE = 20


# Shared list_display for all mesh-based admin classes
MESH_LIST_DISPLAY = [
    "id",
    "valid_date_start",
    "valid_date_end",
    "created",
    "lat_min",
    "lat_max",
    "lon_min",
    "lon_max",
    "name",
    "size",
]


# Shared base admin for mesh models
class BaseMeshAdmin(admin.ModelAdmin):
    ordering = ("-created",)
    readonly_fields = ("md5", "size", "created")
    exclude = ("json",)  # Hide the raw JSON field
    list_per_page = 20

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.defer("json")

        if hasattr(self, "list_select_related") and self.list_select_related:
            queryset = queryset.select_related(*self.list_select_related)

        return queryset


@admin.register(VehicleMesh)
class VehicleMeshAdmin(BaseMeshAdmin):
    list_display = ["id", "vehicle"] + MESH_LIST_DISPLAY[1:]
    list_select_related = ("vehicle",)
    list_filter = ("vehicle", "created")
    search_fields = ("name", "vehicle__vessel_type")


@admin.register(EnvironmentMesh)
class EnvironmentMeshAdmin(BaseMeshAdmin):
    list_display = MESH_LIST_DISPLAY
    list_filter = ("created",)
    search_fields = ("name",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["vessel_type"]


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "display_start",
        "display_end",
        "vehicle_type",
        "display_tags",
        "requested",
        "calculated",
        "job_id",
        "mesh_id",
        "info",
        "polar_route_version",
    ]
    ordering = ("-requested",)
    list_filter = ("tags", "calculated", "requested")
    search_fields = ("start_name", "end_name", "tags__name")

    list_select_related = ("mesh", "vehicle")

    def get_queryset(self, request):
        # Load only the fields necessary for the changelist view
        queryset = super().get_queryset(request)
        return queryset.defer("json", "json_unsmoothed", "mesh__json").prefetch_related(
            "tags"
        )

    def get_fieldsets(self, request, obj=None):
        # Contain the json fields in a collapsed section of the page
        collapsed_fields = ("json", "json_unsmoothed")
        if obj:
            # Get regular model fields excluding collapsed ones and id
            regular_fields = [
                f.name
                for f in self.model._meta.fields
                if f.name not in collapsed_fields + ("id",)
            ]
            # Add tags field (it is a TaggableManager, not a regular field)
            regular_fields.append("tags")

            return [
                (
                    None,
                    {"fields": regular_fields},
                ),
                (
                    "Click to expand JSON fields",
                    {"classes": ["collapse"], "fields": list(collapsed_fields)},
                ),
            ]

        return self.fieldsets

    def display_start(self, obj):
        if obj.start_name:
            return f"{obj.start_name} ({obj.start_lat},{obj.start_lon})"
        else:
            return f"({obj.start_lat},{obj.start_lon})"

    def display_end(self, obj):
        if obj.end_name:
            return f"{obj.end_name} ({obj.end_lat},{obj.end_lon})"
        else:
            return f"({obj.end_lat},{obj.end_lon})"

    def display_tags(self, obj):
        """Display tags as a comma-separated string."""
        tags = obj.tags.all()
        if tags:
            return ", ".join([tag.name for tag in tags])
        return "-"

    def job_id(self, obj):
        job = obj.job_set.latest("datetime")
        return f"{job.id}"

    def mesh_id(self, obj):
        if obj.mesh:
            return f"{obj.mesh.id}"

    def vehicle_type(self, obj):
        if obj.vehicle:
            return obj.vehicle.vessel_type
        return "-"

    display_start.short_description = "Start (lat,lon)"
    display_end.short_description = "End (lat,lon)"
    display_tags.short_description = "Tags"
    job_id.short_description = "Job ID (latest)"
    mesh_id.short_description = "Mesh ID"
    vehicle_type.short_description = "Vehicle Type"

    def get_readonly_fields(self, request, obj=None):
        editable_fields = ("requested", "calculated", "start_name", "end_name", "tags")

        if obj:
            # Return a list of all field names on the model
            return [
                f.name for f in self.model._meta.fields if f.name not in editable_fields
            ]
        return self.readonly_fields


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "datetime",
        "route",
        "get_status",
    ]
    ordering = ("-datetime",)

    def get_status(self, obj):
        """Get current job status from Celery."""
        try:
            return obj.status if obj.status is not None else "UNKNOWN"
        except Exception as e:
            return f"Error: {type(e).__name__}"

    get_status.short_description = "Status"


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "lat",
        "lon",
    ]
    list_filter = ["name"]
    search_fields = ["name"]
    ordering = ["name"]
