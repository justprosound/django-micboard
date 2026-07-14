"""Factories for Micboard user extensions and saved views."""

from __future__ import annotations

import factory

from micboard.models.users.user_profile import UserProfile
from micboard.models.users.user_views import UserView

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.UserProfile")
class UserProfileFactory(ProjectModelFactory):
    """Create a profile for the host project's configured user model."""

    class Meta:
        model = UserProfile

    user = factory.SubFactory("tests.factories.base.UserFactory")


@register_factory("micboard.UserView")
class UserViewFactory(ProjectModelFactory):
    """Create a uniquely named saved view for one user."""

    class Meta:
        model = UserView

    user = factory.SubFactory("tests.factories.base.UserFactory")
    view_name = factory.Sequence(lambda number: f"Factory view {number}")
