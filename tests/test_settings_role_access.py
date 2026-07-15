"""MSP role contracts for dedicated setting-management workflows."""

from __future__ import annotations

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, override_settings
from django.urls import reverse

import pytest

from micboard.admin.settings import SettingAdmin
from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.dtos import SettingsVisibilityScope
from micboard.services.settings.visibility_service import settings_visibility
from tests.factories.base import UserFactory
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

pytestmark = pytest.mark.django_db


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
def test_setting_management_scope_filters_read_only_membership_roles() -> None:
    """Viewer scope remains readable but cannot become a writable setting scope."""
    user = UserFactory()
    organization = OrganizationFactory()
    membership = OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="viewer",
    )

    readable = settings_visibility.for_user(user=user)
    viewer_management = settings_visibility.for_management_user(user=user)
    membership.role = "admin"
    membership.save(update_fields=["role"])
    admin_management = settings_visibility.for_management_user(user=user)

    assert readable.organization_ids == frozenset({organization.pk})
    assert viewer_management == SettingsVisibilityScope(
        organization_ids=frozenset(),
        site_ids=frozenset(),
        manufacturer_ids=frozenset(),
    )
    assert admin_management.organization_ids == frozenset({organization.pk})


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
def test_setting_admin_removes_viewer_management_querysets() -> None:
    """Raw Django change permission cannot expose a viewer to setting actions."""
    user = UserFactory(is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="view_setting"),
        Permission.objects.get(codename="change_setting"),
    )
    organization = OrganizationFactory()
    foreign_organization = OrganizationFactory()
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="viewer",
    )
    definition = SettingDefinition.objects.create(
        key="viewer_setting_scope",
        label="Viewer setting scope",
    )
    visible_setting = Setting.objects.create(
        definition=definition,
        organization_id=organization.pk,
        value="visible",
    )
    Setting.objects.create(
        definition=definition,
        organization_id=foreign_organization.pk,
        value="foreign",
    )
    model_admin = SettingAdmin(Setting, AdminSite())
    get_request = RequestFactory().get("/admin/micboard/setting/")
    get_request.user = user
    post_request = RequestFactory().post("/admin/micboard/setting/")
    post_request.user = user

    assert not model_admin.get_queryset(get_request).exists()
    assert not model_admin.get_queryset(post_request).exists()
    assert not model_admin.has_change_permission(get_request, visible_setting)


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_dedicated_setting_view_denies_non_admin_roles(client, role: str) -> None:
    """Raw Django permissions cannot elevate viewer or operator memberships."""
    user = UserFactory(is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="add_setting"),
        Permission.objects.get(codename="change_setting"),
    )
    OrganizationMembershipFactory(user=user, campus=None, role=role)
    client.force_login(user)

    response = client.get(reverse("micboard:settings_bulk_config"))

    assert response.status_code == 403


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
def test_dedicated_setting_view_allows_organization_admin(client) -> None:
    """An organization-wide admin retains the scoped management workflow."""
    user = UserFactory(is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="add_setting"),
        Permission.objects.get(codename="change_setting"),
    )
    organization = OrganizationFactory()
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="admin",
    )
    client.force_login(user)

    response = client.get(reverse("micboard:settings_bulk_config"))

    assert response.status_code == 200
    organization_ids = set(
        response.context["form"].fields["organization"].queryset.values_list("pk", flat=True)
    )
    assert organization_ids == {organization.pk}


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
def test_manufacturer_setting_view_requires_manufacturer_scope(client) -> None:
    """Organization authority must not expose an empty host-wide workflow."""
    user = UserFactory(is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="add_setting"),
        Permission.objects.get(codename="change_setting"),
    )
    OrganizationMembershipFactory(user=user, campus=None, role="admin")
    client.force_login(user)

    response = client.get(reverse("micboard:settings_manufacturer_config"))

    assert response.status_code == 403
