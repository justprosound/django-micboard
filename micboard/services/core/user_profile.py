"""User profile preference operations."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from micboard.models.users.user_profile import UserProfile

MIN_DISPLAY_WIDTH_PX = 320
MAX_DISPLAY_WIDTH_PX = 16_384


class UserProfileService:
    """Persist validated user profile preferences."""

    @staticmethod
    def set_display_width(*, user: Any, width_px: int) -> UserProfile:
        """Set a user's charger-dashboard width within supported browser limits."""
        if (
            isinstance(width_px, bool)
            or not MIN_DISPLAY_WIDTH_PX <= width_px <= MAX_DISPLAY_WIDTH_PX
        ):
            raise ValidationError(
                {
                    "display_width_px": (
                        f"Display width must be between {MIN_DISPLAY_WIDTH_PX} "
                        f"and {MAX_DISPLAY_WIDTH_PX} pixels."
                    )
                }
            )

        profile, _created = UserProfile.objects.update_or_create(
            user=user,
            defaults={"display_width_px": width_px},
        )
        return profile
