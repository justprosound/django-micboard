"""Django settings for example_project.

⚠️ **DEVELOPMENT/DEMO ONLY** ⚠️

This is an example project for demonstrating django-micboard integration.
DO NOT use these settings in production. See docs/installation.md for
proper configuration guidance.
"""

from __future__ import annotations

import os
from pathlib import Path

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================
# SECURITY WARNING: This is a development/demo configuration only!
# ============================================================================
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# Applications
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.import_export",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "import_export",
    "adminsortable2",
    "simple_history",
    "rangefilter",
    # Core app
    "micboard",
    "micboard.chargers",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "example_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "example_project.wsgi.application"
ASGI_APPLICATION = "example_project.asgi.application"

# Database (uses repo-level db.sqlite3)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db.sqlite3"),
    }
}

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sites framework
SITE_ID = 1

# Optional Micboard-specific config
MICBOARD_CONFIG = {
    # Single server configuration (backward compatible)
    "SHURE_API_BASE_URL": os.environ.get("MICBOARD_SHURE_API_BASE_URL", "https://localhost:10000"),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
    "SHURE_API_VERIFY_SSL": os.environ.get("MICBOARD_SHURE_API_VERIFY_SSL", "false").lower()
    in ("true", "1", "yes"),
    # Multi-location API servers configuration
    # Each server can be associated with a specific location
    "MANUFACTURER_API_SERVERS": {
        # "main_venue": {
        #     "manufacturer": "shure",
        #     "base_url": "https://shure-api-1.example.com:10000",
        #     "shared_key": os.environ.get("SHURE_API_KEY_MAIN"),
        #     "verify_ssl": False,
        #     "location_id": 1,  # Optional: Django Location model ID
        #     "enabled": True,
        # },
        # "satellite_venue": {
        #     "manufacturer": "shure",
        #     "base_url": "https://shure-api-2.example.com:10000",
        #     "shared_key": os.environ.get("SHURE_API_KEY_SAT"),
        #     "verify_ssl": False,
        #     "location_id": 2,
        #     "enabled": True,
        # },
    },
    # Audit retention
    "ACTIVITY_LOG_RETENTION_DAYS": 90,
    "SERVICE_SYNC_LOG_RETENTION_DAYS": 30,
    "API_HEALTH_LOG_RETENTION_DAYS": 7,
    "AUDIT_ARCHIVE_PATH": "audit_archives",
}
