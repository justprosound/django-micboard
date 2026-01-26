"""User-specific view configurations and layout preferences.

Stores per-user dashboard configurations including selected views,
filter preferences, and display settings. Enables personalized monitoring
experiences for different operators and administrators.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class UserView(models.Model):
    """Persist a user's saved dashboard view configuration."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    view_name = models.CharField(max_length=255)
    last_accessed = models.DateTimeField(default=timezone.now)

    class Meta:
        """Model metadata for uniqueness and naming."""

        unique_together = ("user", "view_name")

    def __str__(self) -> str:
        """Return a readable label for the stored view."""
        return f"{self.user.username}'s view: {self.view_name}"
