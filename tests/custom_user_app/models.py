from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    """Host-owned user model used to verify Micboard remains pluggable."""

    class Meta:
        app_label = "custom_user_app"
