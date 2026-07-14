"""Security and workload contracts for queued API server health checks."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import override_settings

import pytest

from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.integrations.api_server_service import (
    MAX_API_SERVER_HEALTH_CHECK_BATCH,
    APIServerConnectionService,
)
from micboard.tasks.monitoring.health import check_selected_api_server_connections
from tests.factories.base import UserFactory
from tests.factories.hardware import ManufacturerAPIServerFactory


@pytest.mark.django_db
def test_api_server_batch_rechecks_worker_permission_before_external_io() -> None:
    """Revoked or missing admin access prevents every queued connection attempt."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    server = ManufacturerAPIServerFactory()

    with patch.object(APIServerConnectionService, "test_connection_and_record") as check:
        result = APIServerConnectionService.test_selected_connections(
            api_server_ids=[server.pk],
            actor_id=actor.pk,
        )

    check.assert_not_called()
    assert result.model_dump() == {
        "requested": 1,
        "checked": 0,
        "failed": 0,
        "missing": 0,
        "denied": True,
        "truncated": False,
    }


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=True)
def test_api_server_batch_rechecks_platform_global_scope() -> None:
    """A model permission alone cannot authorize global credentials in tenant modes."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    actor.user_permissions.add(Permission.objects.get(codename="change_manufacturerapiserver"))
    server = ManufacturerAPIServerFactory()

    with patch.object(APIServerConnectionService, "test_connection_and_record") as check:
        result = APIServerConnectionService.test_selected_connections(
            api_server_ids=[server.pk],
            actor_id=actor.pk,
        )

    check.assert_not_called()
    assert result.denied is True
    assert result.checked == 0


@pytest.mark.django_db
@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
def test_api_server_batch_honors_restricted_superuser_policy() -> None:
    """Restricted superusers cannot regain platform-global access in a queued task."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=True)
    server = ManufacturerAPIServerFactory()

    with patch.object(APIServerConnectionService, "test_connection_and_record") as check:
        result = APIServerConnectionService.test_selected_connections(
            api_server_ids=[server.pk],
            actor_id=actor.pk,
        )

    check.assert_not_called()
    assert result.denied is True


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
