from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    last_login = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Profile for {self.user.username}"
