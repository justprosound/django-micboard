"""Host-boundary tests for Micboard's user-profile admin."""

from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from micboard.admin.users import UserProfileAdmin, register_user_profile_admin
from micboard.models.users.user_profile import UserProfile


def test_profile_registration_preserves_absent_host_user_registration() -> None:
    """A host that omits User from admin remains unchanged."""
    site = AdminSite()

    register_user_profile_admin(site)

    assert not site.is_registered(User)
    assert isinstance(site._registry[UserProfile], UserProfileAdmin)


def test_profile_registration_preserves_custom_host_user_admin() -> None:
    """A host's custom User admin remains registered byte-for-byte."""

    class CustomUserAdmin(BaseUserAdmin):
        pass

    site = AdminSite()
    site.register(User, CustomUserAdmin)
    host_admin = site._registry[User]

    register_user_profile_admin(site)
    register_user_profile_admin(site)

    assert site._registry[User] is host_admin
    assert isinstance(site._registry[UserProfile], UserProfileAdmin)
