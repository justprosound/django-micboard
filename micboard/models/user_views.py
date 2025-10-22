from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class UserView(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    view_name = models.CharField(max_length=255)
    last_accessed = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "view_name")

    def __str__(self) -> str:
        return f"{self.user.username}'s view: {self.view_name}"
