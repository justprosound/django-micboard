"""Django settings for a host that installs Micboard without optional apps."""

from tests.settings import *  # noqa: F403
from tests.settings import INSTALLED_APPS

INSTALLED_APPS = [
    app for app in INSTALLED_APPS if app not in {"huey.contrib.djhuey", "micboard.multitenancy"}
]
