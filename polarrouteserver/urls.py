from django.contrib import admin
from django.conf import settings
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from health_check.views import HealthCheckView

from polarrouteserver.route_api import views

# Create a router and register our ViewSets with it.
router = DefaultRouter()
router.register(r"locations", views.LocationViewSet, basename="location")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/route",
        views.RouteRequestView.as_view(),
        name="route_list_create",
    ),
    path(
        "api/route/<int:id>",
        views.RouteDetailView.as_view(),
        name="route_detail",
    ),
    path(
        "api/job/<uuid:id>",
        views.JobView.as_view(),
        name="job_detail",
    ),
    path(
        "api/recent_routes",
        views.RecentRoutesView.as_view(),
        name="recent_routes_list",
    ),
    path(
        "api/vehicle",
        views.VehicleRequestView.as_view(),  # POST and GET (list all)
        name="vehicle_list_create",
    ),
    path(
        "api/vehicle/<str:vessel_type>/",
        views.VehicleDetailView.as_view(),  # GET/DELETE by vessel_type
        name="vehicle_detail",
    ),
    path(
        "api/vehicle/available",
        views.VehicleTypeListView.as_view(),
        name="vehicle_type_list",
    ),
    path("api/mesh/<int:id>", views.MeshView.as_view(), name="mesh_detail"),
    path(
        "api/evaluate_route", views.EvaluateRouteView.as_view(), name="evaluate_route"
    ),
    path(
        "health/",
        HealthCheckView.as_view(checks=settings.HEALTH_CHECKS),
        name="health_check",
    ),
]

# noqa
try:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
except:  # noqa
    pass
