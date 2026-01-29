"""Test URL configuration for pytest-django."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("micboard.urls")),
]
