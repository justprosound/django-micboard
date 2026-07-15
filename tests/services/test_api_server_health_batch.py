"""Security and workload contracts for queued API server health checks."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, override_settings

import pytest

from micboard.admin.integrations import ManufacturerAPIServerAdmin
from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.integrations.api_server_service import (
    MAX_API_SERVER_HEALTH_CHECK_BATCH,
    APIServerConnectionService,
)
from micboard.tasks.monitoring.health import check_selected_api_server_connections
from tests.factories.base import UserFactory
from tests.factories.hardware import ManufacturerAPIServerFactory
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory


def _grant_api_server_change_permission(actor) -> None:
    """Grant the model permission independently rechecked by the worker."""
    actor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="micboard",
            codename="change_manufacturerapiserver",
        )
    )


@pytest.mark.parametrize(
    ("is_active", "is_staff", "has_permission", "expected_denied"),
    [
        pytest.param(False, True, True, True, id="inactive"),
        pytest.param(True, False, True, True, id="non-staff"),
        pytest.param(True, True, False, True, id="permission-revoked"),
        pytest.param(True, True, True, False, id="authorized"),
    ],
)
@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False)
def test_api_server_batch_rechecks_worker_actor_state_before_external_io(
    is_active: bool,
    is_staff: bool,
    has_permission: bool,
    expected_denied: bool,
) -> None:
    """Queued work independently rechecks actor state and Django permission."""
    actor = UserFactory(
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=False,
    )
    if has_permission:
        _grant_api_server_change_permission(actor)
    server = ManufacturerAPIServerFactory()

    with patch.object(APIServerConnectionService, "test_connection_and_record") as check:
        result = APIServerConnectionService.test_selected_connections(
            api_server_ids=[server.pk],
            actor_id=actor.pk,
        )

    assert result.denied is expected_denied
    assert result.checked == int(not expected_denied)
    if expected_denied:
        check.assert_not_called()
    else:
        check.assert_called_once_with(server)


@pytest.mark.parametrize(
    (
        "msp_enabled",
        "multi_site_enabled",
        "allow_cross_org_view",
        "is_superuser",
        "membership_role",
        "expected_allowed",
    ),
    [
        pytest.param(False, False, False, False, None, True, id="single-tenant-staff"),
        pytest.param(True, False, False, False, "viewer", False, id="msp-viewer"),
        pytest.param(True, False, True, False, "operator", False, id="msp-operator"),
        pytest.param(True, False, False, False, "admin", False, id="msp-admin"),
        pytest.param(True, True, True, False, "owner", False, id="multisite-owner"),
        pytest.param(True, False, False, True, None, True, id="restricted-msp-superuser"),
        pytest.param(True, False, True, True, None, True, id="cross-org-superuser"),
        pytest.param(False, True, False, True, None, True, id="multisite-superuser"),
        pytest.param(True, True, False, True, None, True, id="msp-multisite-superuser"),
    ],
)
@pytest.mark.django_db
def test_api_server_worker_matches_request_platform_global_policy(
    msp_enabled: bool,
    multi_site_enabled: bool,
    allow_cross_org_view: bool,
    is_superuser: bool,
    membership_role: str | None,
    expected_allowed: bool,
) -> None:
    """Admin requests and queued workers share one platform-global authorization decision."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=is_superuser)
    if not is_superuser:
        _grant_api_server_change_permission(actor)
    if membership_role is not None:
        OrganizationMembershipFactory(
            user=actor,
            organization=OrganizationFactory(),
            campus=None,
            role=membership_role,
        )
    server = ManufacturerAPIServerFactory()
    request = RequestFactory().post("/admin/micboard/manufacturerapiserver/")
    request.user = actor
    model_admin = ManufacturerAPIServerAdmin(ManufacturerAPIServer, AdminSite())

    with (
        override_settings(
            MICBOARD_MSP_ENABLED=msp_enabled,
            MICBOARD_MULTI_SITE_MODE=multi_site_enabled,
            MICBOARD_ALLOW_CROSS_ORG_VIEW=allow_cross_org_view,
        ),
        patch.object(APIServerConnectionService, "test_connection_and_record") as check,
    ):
        request_allowed = model_admin.has_change_permission(request, server)
        result = APIServerConnectionService.test_selected_connections(
            api_server_ids=[server.pk],
            actor_id=actor.pk,
        )

    assert request_allowed is expected_allowed
    assert (not result.denied) is expected_allowed
    if expected_allowed:
        check.assert_called_once_with(server)
    else:
        check.assert_not_called()


@pytest.mark.django_db
def test_api_server_batch_is_exact_bounded_and_serializable() -> None:
    """A privileged worker checks only existing selected rows up to the hard batch cap."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=True)
    servers = [
        ManufacturerAPIServerFactory(status=ManufacturerAPIServer.Status.UNKNOWN)
        for _ in range(MAX_API_SERVER_HEALTH_CHECK_BATCH + 1)
    ]
    requested_ids = [server.pk for server in reversed(servers)]

    def mark_checked(server: ManufacturerAPIServer) -> None:
        server.status = ManufacturerAPIServer.Status.ACTIVE

    with patch.object(
        APIServerConnectionService,
        "test_connection_and_record",
        side_effect=mark_checked,
    ) as check:
        result = check_selected_api_server_connections(requested_ids, actor.pk)

    assert check.call_count == MAX_API_SERVER_HEALTH_CHECK_BATCH
    checked_ids = [call.args[0].pk for call in check.call_args_list]
    assert checked_ids == sorted(requested_ids[:MAX_API_SERVER_HEALTH_CHECK_BATCH])
    assert result == {
        "requested": MAX_API_SERVER_HEALTH_CHECK_BATCH + 1,
        "checked": MAX_API_SERVER_HEALTH_CHECK_BATCH,
        "failed": 0,
        "missing": 0,
        "denied": False,
        "truncated": True,
    }


@pytest.mark.django_db
def test_api_server_batch_reports_missing_and_failed_rows() -> None:
    """Batch accounting distinguishes absent rows from recorded connection failures."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=True)
    server = ManufacturerAPIServerFactory(status=ManufacturerAPIServer.Status.UNKNOWN)

    def mark_failed(selected: ManufacturerAPIServer) -> None:
        selected.status = ManufacturerAPIServer.Status.ERROR

    with patch.object(
        APIServerConnectionService,
        "test_connection_and_record",
        side_effect=mark_failed,
    ):
        result = APIServerConnectionService.test_selected_connections(
            api_server_ids=[server.pk, server.pk + 100_000],
            actor_id=actor.pk,
        )

    assert result.checked == 1
    assert result.failed == 1
    assert result.missing == 1
