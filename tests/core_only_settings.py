"""Django settings for a host that installs Micboard without optional apps."""

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

INSTALLED_APPS = [
    app
    for app in BASE_INSTALLED_APPS
    if app not in {"huey.contrib.djhuey", "micboard.multitenancy"}
]

__all__ = (
    "ALLOWED_HOSTS",
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
