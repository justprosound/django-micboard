"""Django settings for exercising Micboard inside a custom-user host."""

from tests.settings import (
    ALLOWED_HOSTS,
    BASE_DIR,
    DATABASES,
    DEBUG,
    DEFAULT_AUTO_FIELD,
    HUEY,
    MEDIA_ROOT,
    MEDIA_URL,
    MIDDLEWARE,
    ROOT_URLCONF,
    SECRET_KEY,
    SITE_ID,
    STATIC_ROOT,
    STATIC_URL,
    TEMPLATES,
    TESTING,
)
from tests.settings import INSTALLED_APPS as BASE_INSTALLED_APPS

INSTALLED_APPS = [*BASE_INSTALLED_APPS, "tests.custom_user_app"]
AUTH_USER_MODEL = "custom_user_app.CustomUser"

__all__ = (
    "ALLOWED_HOSTS",
    "AUTH_USER_MODEL",
    "BASE_DIR",
    "DATABASES",
    "DEBUG",
    "DEFAULT_AUTO_FIELD",
    "HUEY",
    "INSTALLED_APPS",
    "MEDIA_ROOT",
    "MEDIA_URL",
    "MIDDLEWARE",
    "ROOT_URLCONF",
    "SECRET_KEY",
    "SITE_ID",
    "STATIC_ROOT",
    "STATIC_URL",
    "TEMPLATES",
    "TESTING",
)
