"""User-related signal handlers for the micboard app."""

# User-related signal handlers for the micboard app.
from __future__ import annotations

import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from micboard.models import UserProfile

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.last_login = timezone.now()
    profile.save()
