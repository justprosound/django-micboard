"""Django settings for exercising Micboard inside a custom-user host."""

from tests.settings import *  # noqa: F403
from tests.settings import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "tests.custom_user_app"]
AUTH_USER_MODEL = "custom_user_app.CustomUser"
