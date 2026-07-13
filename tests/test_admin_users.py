"""Host-boundary tests for Micboard's User admin enhancement."""

from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from micboard.admin.users import UserAdmin, configure_user_admin


def test_configure_user_admin_preserves_absent_host_registration() -> None:
    """A host that omits User from admin must remain valid and unchanged."""
    site = AdminSite()

    configure_user_admin(site)

    assert not site.is_registered(User)


def test_configure_user_admin_replaces_existing_registration_idempotently() -> None:
    """An existing User admin receives the Micboard profile enhancement once."""
    site = AdminSite()
    site.register(User, BaseUserAdmin)

    configure_user_admin(site)
    configure_user_admin(site)

    assert isinstance(site._registry[User], UserAdmin)
