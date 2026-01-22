from django.contrib import admin
from django.urls import include, path

# New API router and admin dashboard imports
from micboard.api.v1.routers import router as api_v2_router
from micboard.admin.dashboard import (
    admin_dashboard,
    api_dashboard_data,
    api_manufacturer_status,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("micboard.urls")),
    # New DRF router-based API (mounted under /api/v2 to avoid conflicts)
    path("api/v2/", include(api_v2_router.urls)),
    # Admin dashboard routes
    path("admin/dashboard/", admin_dashboard, name="admin-dashboard"),
    path("api/dashboard/", api_dashboard_data, name="api-dashboard-data"),
    path(
        "api/manufacturer/<str:manufacturer_code>/status/",
        api_manufacturer_status,
        name="api-manufacturer-status",
    ),
]
