"""Coverage for multitenancy admin and request resolution."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.http import HttpResponse
from django.test import override_settings

import pytest

from micboard.multitenancy.admin import SuperuserOnlyAdmin
from micboard.multitenancy.middleware import (
    TenantMiddleware,
    _get_org_from_membership,
    _get_org_from_session,
    _get_org_from_subdomain,
    _get_org_from_user_profile,
    get_current_campus,
    get_current_organization,
)
from micboard.multitenancy.models import Organization


class _AdminModelMeta:
    app_label = "tests"
    model_name = "admin_model"
    verbose_name = "admin model"
    verbose_name_plural = "admin models"
    abstract = False
    swapped = False


class _AdminModel:
    _meta = _AdminModelMeta()


@pytest.mark.parametrize("is_superuser", [False, True])
def test_superuser_only_admin_enforces_every_permission(is_superuser: bool) -> None:
    model_admin = SuperuserOnlyAdmin(_AdminModel, AdminSite())
    queryset = MagicMock()
    model_admin.model._default_manager = MagicMock()  # type: ignore[attr-defined]
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=is_superuser))

    with patch("django.contrib.admin.ModelAdmin.get_queryset", return_value=queryset):
        result = model_admin.get_queryset(request)

    assert result is (queryset if is_superuser else queryset.none.return_value)
    assert model_admin.has_module_permission(request) is is_superuser
    assert model_admin.has_view_permission(request, object()) is is_superuser
    assert model_admin.has_add_permission(request) is is_superuser
    assert model_admin.has_change_permission(request, object()) is is_superuser
    assert model_admin.has_delete_permission(request, object()) is is_superuser


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_msp_admin_definitions_delegate_counts_and_membership_authorship() -> None:
    import micboard.multitenancy.admin as tenant_admin

    def identity_register(*models: Any, **options: Any) -> Any:
        del models, options

        def preserve_class(cls: type) -> type:
            return cls

        return preserve_class

    with patch("django.contrib.admin.register", identity_register):
        reloaded = importlib.reload(tenant_admin)

    organization_admin = reloaded.OrganizationAdmin.__new__(reloaded.OrganizationAdmin)
    organization = object()
    with patch(
        "micboard.services.multitenancy.organization_service.get_device_count", return_value=12
    ) as get_count:
        assert organization_admin.device_count(organization) == 12
    get_count.assert_called_once_with(organization)

    membership_admin = reloaded.OrganizationMembershipAdmin.__new__(
        reloaded.OrganizationMembershipAdmin
    )
    membership_admin.model = MagicMock()
    membership_admin.admin_site = AdminSite()
    request = SimpleNamespace(user=object())
    membership = object()
    form = MagicMock()
    with (
        patch(
            "micboard.services.multitenancy.organization_service.set_created_by",
            return_value=membership,
        ) as set_created_by,
        patch("django.contrib.admin.ModelAdmin.save_model") as save_model,
    ):
        membership_admin.save_model(request, membership, form, change=False)
        membership_admin.save_model(request, membership, form, change=True)

    set_created_by.assert_called_once_with(membership, request.user)
    assert save_model.call_count == 2

    with override_settings(MICBOARD_MSP_ENABLED=False):
        importlib.reload(tenant_admin)


def _tenant_request(**overrides: Any) -> Any:
    values = {
        "user": SimpleNamespace(is_authenticated=False, is_superuser=False),
        "session": {},
        "get_host": lambda: "tenant.example.test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_tenant_resolvers_cover_empty_inactive_and_disabled_contexts() -> None:
    request = _tenant_request()
    assert _get_org_from_session(request) is None
    assert _get_org_from_session(SimpleNamespace(user=request.user)) is None
    assert _get_org_from_user_profile(request) is None
    missing_profile = _tenant_request(
        user=SimpleNamespace(is_authenticated=True, is_superuser=False)
    )
    assert _get_org_from_user_profile(missing_profile) is None
    inactive_profile = _tenant_request(
        user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            profile=SimpleNamespace(default_organization=SimpleNamespace(is_active=False)),
        )
    )
    assert _get_org_from_user_profile(inactive_profile) is None
    assert _get_org_from_membership(request) is None
    with override_settings(MICBOARD_SUBDOMAIN_ROUTING=False):
        assert _get_org_from_subdomain(request) is None
    with override_settings(MICBOARD_MSP_ENABLED=False):
        assert get_current_organization(request) is None
        assert get_current_campus(request) is None


def test_tenant_membership_and_subdomain_missing_rows_return_none() -> None:
    authenticated = _tenant_request(user=SimpleNamespace(is_authenticated=True, is_superuser=False))
    chain = MagicMock()
    chain.select_related.return_value.order_by.return_value.first.return_value = None
    with patch(
        "micboard.multitenancy.models.OrganizationMembership._default_manager.filter",
        return_value=chain,
    ):
        assert _get_org_from_membership(authenticated) is None
    chain.select_related.return_value.order_by.return_value.first.return_value = SimpleNamespace(
        organization=SimpleNamespace(is_active=False)
    )
    with patch(
        "micboard.multitenancy.models.OrganizationMembership._default_manager.filter",
        return_value=chain,
    ):
        assert _get_org_from_membership(authenticated) is None

    with (
        override_settings(MICBOARD_SUBDOMAIN_ROUTING=True, MICBOARD_ROOT_DOMAIN="example.test"),
        patch.object(
            Organization._default_manager,
            "get",
            side_effect=Organization.DoesNotExist,
        ),
    ):
        assert _get_org_from_subdomain(authenticated) is None

    anonymous_with_session = _tenant_request(session={"current_organization_id": 4})
    with patch.object(
        Organization._default_manager,
        "get",
        return_value=SimpleNamespace(pk=4, is_active=True),
    ):
        assert _get_org_from_session(anonymous_with_session) is None


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_current_tenant_resolution_falls_through_and_campus_handles_no_restriction() -> None:
    request = _tenant_request(
        user=SimpleNamespace(is_authenticated=True, is_superuser=False),
        organization=SimpleNamespace(pk=3),
    )
    with (
        patch("micboard.multitenancy.middleware._get_org_from_session", return_value=None),
        patch("micboard.multitenancy.middleware._get_org_from_user_profile", return_value=None),
        patch("micboard.multitenancy.middleware._get_org_from_membership", return_value=None),
        patch("micboard.multitenancy.middleware._get_org_from_subdomain", return_value="subdomain"),
    ):
        assert get_current_organization(request) == "subdomain"

    membership = MagicMock(campus_id=None)
    membership_filter = MagicMock()
    membership_filter.first.return_value = membership
    with patch(
        "micboard.multitenancy.models.OrganizationMembership._default_manager.filter",
        return_value=membership_filter,
    ):
        assert get_current_campus(request) is None
    request.session = {"current_campus_id": 8}
    assert get_current_campus(request) == 8


@override_settings(MICBOARD_MSP_ENABLED=True)
@pytest.mark.parametrize("source", ["session", "profile", "membership"])
def test_current_organization_returns_first_available_authenticated_source(source: str) -> None:
    values = {
        "session": "session-org" if source == "session" else None,
        "profile": "profile-org" if source == "profile" else None,
        "membership": "membership-org" if source == "membership" else None,
    }
    with (
        patch(
            "micboard.multitenancy.middleware._get_org_from_session",
            return_value=values["session"],
        ),
        patch(
            "micboard.multitenancy.middleware._get_org_from_user_profile",
            return_value=values["profile"],
        ),
        patch(
            "micboard.multitenancy.middleware._get_org_from_membership",
            return_value=values["membership"],
        ),
    ):
        assert get_current_organization(_tenant_request()) == values[source]


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_current_campus_handles_missing_session_user_and_organization() -> None:
    no_session = SimpleNamespace(user=SimpleNamespace(is_authenticated=False, is_superuser=False))
    assert get_current_campus(no_session) is None
    unauthenticated = _tenant_request(organization=object())
    assert get_current_campus(unauthenticated) is None
    no_organization = _tenant_request(
        user=SimpleNamespace(is_authenticated=True, is_superuser=False),
        organization=None,
    )
    assert get_current_campus(no_organization) is None


def test_tenant_middleware_attaches_lazy_values_and_returns_downstream_response() -> None:
    request = _tenant_request()
    response = HttpResponse("ok")
    middleware = TenantMiddleware(lambda incoming: response)
    assert middleware(request) is response
    with (
        patch(
            "micboard.multitenancy.middleware.get_current_organization",
            return_value="organization",
        ),
        patch("micboard.multitenancy.middleware.get_current_campus", return_value=7),
    ):
        assert str(request.organization) == "organization"
        assert request.campus_id == 7
