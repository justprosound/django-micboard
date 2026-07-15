"""User profile preference service contracts."""

from django.core.exceptions import ValidationError

import pytest

from micboard.services.core.user_profile import UserProfileService
from tests.factories.base import UserFactory

pytestmark = pytest.mark.django_db


def test_display_width_update_creates_then_updates_profile() -> None:
    """A validated preference has one durable profile row per user."""
    user = UserFactory()

    profile = UserProfileService.set_display_width(user=user, width_px=1200)
    updated = UserProfileService.set_display_width(user=user, width_px=3840)

    assert updated.pk == profile.pk
    assert updated.display_width_px == 3840


@pytest.mark.parametrize("width_px", [True, 319, 16_385])
def test_display_width_update_rejects_unsupported_values(width_px: int) -> None:
    """Direct service callers cannot bypass the dashboard form's bounds."""
    with pytest.raises(ValidationError, match="Display width must be between"):
        UserProfileService.set_display_width(user=UserFactory(), width_px=width_px)
