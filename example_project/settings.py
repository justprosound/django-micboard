"""Django settings for example_project.
# ruff: noqa: E402  # See Django bootstrap note below.

⚠️ **DEVELOPMENT/DEMO ONLY** ⚠️

This is an example project for demonstrating django-micboard integration.
DO NOT use these settings in production. See docs/installation.md for
proper configuration guidance.
"""

from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================
# SECURITY WARNING: This is a development/demo configuration only!
# ============================================================================
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

HUEY = {
    "huey_class": "huey.SqliteHuey",
    "name": "micboard-example",
    "filename": str(BASE_DIR / ".huey.db"),
    "immediate": DEBUG,
}


# Helper to check if optional packages are installed
def _is_package_installed(package_name: str) -> bool:
    return find_spec(package_name.replace("-", "_")) is not None


# Applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "huey.contrib.djhuey",
    # Core app
    "micboard",
    "micboard.chargers",
]

# Optional admin enhancements (only if installed)
_has_unfold = _is_package_installed("unfold")

if _has_unfold:
    INSTALLED_APPS.insert(0, "unfold")
    INSTALLED_APPS.insert(1, "unfold.contrib.filters")

if _is_package_installed("adminsortable2"):
    INSTALLED_APPS.append("adminsortable2")

if _is_package_installed("simple_history"):
    INSTALLED_APPS.append("simple_history")

if _is_package_installed("rangefilter"):
    INSTALLED_APPS.append("rangefilter")

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

# Database (uses repo-level db.sqlite3 unless a database URL is provided). `DATABASE_URL` is
# accepted because hosting platforms inject that name automatically when a database is
# attached; the Django-prefixed name wins when both are set.
DATABASE_URL = os.environ.get("DJANGO_DATABASE_URL") or os.environ.get("DATABASE_URL")
if DATABASE_URL:
    try:
        import dj_database_url
    except ImportError as exc:  # pragma: no cover - depends on the installed extras
        # Falling back to SQLite here would quietly ignore the configured database and
        # then fail the micboard.E001 production-backend check with a confusing message.
        raise ImproperlyConfigured(
            "A database URL is configured but dj-database-url is not installed. "
            "Install the 'demo' extra, or unset the database URL to use SQLite."
        ) from exc

    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
        )
    }
else:
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

# Exact hosts that persisted Manufacturer API Server rows may contact. Keep
# this explicit so an editable admin URL cannot become a credential-bearing
# server-side request to an arbitrary destination.
MICBOARD_API_SERVER_ALLOWED_HOSTS = tuple(
    host.strip()
    for host in os.environ.get("MICBOARD_API_SERVER_ALLOWED_HOSTS", "localhost").split(",")
    if host.strip()
)

LOGIN_REDIRECT_URL = "/admin/"
# Optional Micboard-specific config
import typing as t  # noqa: E402 -- needed after Django bootstrap

MICBOARD_CONFIG: dict[str, t.Any] = {
    # Single server configuration (backward compatible)
    "SHURE_API_BASE_URL": os.environ.get("MICBOARD_SHURE_API_BASE_URL", "https://localhost:10000"),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
    # Multi-location API servers configuration
    # Each server can be associated with a specific location
    "MANUFACTURER_API_SERVERS": {
        # "main_venue": {
        #     "manufacturer": "shure",
        #     "base_url": "https://shure-api-1.example.com:10000",
        #     "shared_key": os.environ.get("SHURE_API_KEY_MAIN"),
        #     "location_id": 1,  # Optional: Django Location model ID
        #     "enabled": True,
        # },
        # "satellite_venue": {
        #     "manufacturer": "shure",
        #     "base_url": "https://shure-api-2.example.com:10000",
        #     "shared_key": os.environ.get("SHURE_API_KEY_SAT"),
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

# ============================================================================
# Public demo deployment
# ============================================================================
# Only engaged when the environment asks for it, so local development keeps the
# permissive defaults above. See docs/demo-deployment.md.
if _is_package_installed("whitenoise"):
    # Immediately after SecurityMiddleware, as WhiteNoise requires.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            # Compression without a manifest. The manifest variant post-processes CSS and
            # hard-fails on a missing referenced file, and micboard/static/micboard/css/
            # theme.css carries 96 references to IBM Plex Mono font files that are not
            # vendored in this repository: the stylesheet is compiled output whose SCSS
            # imported @ibm/plex from node_modules. Hashed filenames are not worth
            # rewriting generated CSS for on a demo deployment.
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }

# A platform such as Render terminates TLS at its proxy, so Django needs to be told
# that a forwarded request was secure before it will set secure cookies.
if os.environ.get("DJANGO_BEHIND_TLS_PROXY", "False").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    # One hour, and deliberately without includeSubDomains or preload: a demo on a
    # shared platform hostname has no business setting a domain-wide policy.
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "3600"))

# Django requires the scheme-qualified origin for admin logins behind a proxy.
CSRF_TRUSTED_ORIGINS = [
    origin for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin
]
