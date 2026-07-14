"""Secure connectivity checks for persisted manufacturer API servers."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.integrations.dtos import APIServerHealthCheckBatchResult
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

MAX_API_SERVER_HEALTH_CHECK_BATCH = 20


class APIServerConnectionService:
    """Validate and test an explicitly configured manufacturer endpoint."""

    @staticmethod
    def validate_destination(base_url: str) -> None:
        """Require an endpoint host to appear in the deployment allowlist."""
        hostname = (urlsplit(base_url).hostname or "").rstrip(".").lower()
        configured_hosts = getattr(settings, "MICBOARD_API_SERVER_ALLOWED_HOSTS", ())
        if isinstance(configured_hosts, str):
            configured_hosts = configured_hosts.split(",")
        allowed_hosts = {
            str(host).strip().rstrip(".").lower() for host in configured_hosts if str(host).strip()
        }
        if not hostname or hostname not in allowed_hosts:
            raise ValidationError(
                "API server host is not listed in MICBOARD_API_SERVER_ALLOWED_HOSTS."
            )

    @classmethod
    def fetch_shure_devices(
        cls,
        *,
        base_url: str,
        shared_key: str,
    ) -> list[dict[str, Any]]:
        """Fetch devices using one explicitly allowed destination and credential."""
        cls.validate_destination(base_url)

        from micboard.integrations.shure.client import ShureSystemAPIClient

        with ShureSystemAPIClient(base_url=base_url, shared_key=shared_key) as client:
            return client.devices.get_devices() or []

    @classmethod
    def fetch_server_devices(
        cls,
        server: ManufacturerAPIServer,
    ) -> list[dict[str, Any]] | None:
        """Fetch devices for a supported persisted server, scoped to that row."""
        if server.manufacturer != ManufacturerAPIServer.Manufacturer.SHURE:
            return None
        return cls.fetch_shure_devices(
            base_url=server.base_url,
            shared_key=server.shared_key,
        )

    @classmethod
    def test_connection(cls, server: ManufacturerAPIServer) -> None:
        """Test one server using only that row's destination and credential."""
        if server.manufacturer != ManufacturerAPIServer.Manufacturer.SHURE:
            cls.validate_destination(server.base_url)
            server.status = ManufacturerAPIServer.Status.UNKNOWN
            server.status_message = f"Health check not implemented for {server.manufacturer}"
            server.save(update_fields=["status", "status_message", "updated_at"])
            return

        devices = cls.fetch_server_devices(server)
        if devices is None:
            return

        server.status = ManufacturerAPIServer.Status.ACTIVE
        server.status_message = f"Connection successful ({len(devices or [])} devices found)"
        server.last_health_check = timezone.now()
        server.save(update_fields=["status", "status_message", "last_health_check", "updated_at"])

    @classmethod
    def test_connection_and_record(cls, server: ManufacturerAPIServer) -> None:
        """Test one server and persist a bounded failure state on error."""
        try:
            cls.test_connection(server)
        except Exception as exc:
            logger.exception(
                "Manufacturer API server health check failed for server %s",
                server.pk,
                exc_info=sanitized_exception_info(exc),
            )
            server.status = ManufacturerAPIServer.Status.ERROR
            server.status_message = f"Connection failed ({type(exc).__name__})"
            server.last_health_check = timezone.now()
            server.save(
                update_fields=["status", "status_message", "last_health_check", "updated_at"]
            )

    @classmethod
    def test_selected_connections(
        cls,
        *,
        api_server_ids: list[int],
        actor_id: int,
        using: str = "default",
    ) -> APIServerHealthCheckBatchResult:
        """Test an exact, bounded selection after rechecking the actor's permission."""
        requested = len(api_server_ids)
        truncated = requested > MAX_API_SERVER_HEALTH_CHECK_BATCH
        selected_ids = tuple(
            dict.fromkeys(
                server_id
                for server_id in api_server_ids[:MAX_API_SERVER_HEALTH_CHECK_BATCH]
                if isinstance(server_id, int) and not isinstance(server_id, bool) and server_id > 0
            )
        )

        user_model = get_user_model()
        try:
            actor = user_model._default_manager.using(using).get(pk=actor_id)
        except user_model.DoesNotExist:
            actor = None

        if (
            actor is None
            or not actor.is_active
            or not actor.is_staff
            or not actor.has_perm("micboard.change_manufacturerapiserver")
            or not cls._actor_has_platform_scope(actor)
        ):
            logger.warning(
                "Denied queued API server health-check batch for actor %s",
                actor_id,
            )
            return APIServerHealthCheckBatchResult(
                requested=requested,
                checked=0,
                failed=0,
                missing=0,
                denied=True,
                truncated=truncated,
            )

        servers = list(
            ManufacturerAPIServer._default_manager.using(using)
            .filter(pk__in=selected_ids)
            .order_by("pk")
        )
        failed = 0
        for server in servers:
            try:
                cls.test_connection_and_record(server)
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Queued API server health check could not record server %s",
                    server.pk,
                    exc_info=sanitized_exception_info(exc),
                )
                continue
            if server.status == ManufacturerAPIServer.Status.ERROR:
                failed += 1

        return APIServerHealthCheckBatchResult(
            requested=requested,
            checked=len(servers),
            failed=failed,
            missing=len(selected_ids) - len(servers),
            denied=False,
            truncated=truncated,
        )

    @staticmethod
    def _actor_has_platform_scope(actor: Any) -> bool:
        """Mirror admin policy for credential-bearing platform-global rows."""
        msp_enabled = getattr(settings, "MICBOARD_MSP_ENABLED", False)
        multi_site_enabled = getattr(settings, "MICBOARD_MULTI_SITE_MODE", False)
        if not (msp_enabled or multi_site_enabled):
            return True
        if not actor.is_superuser:
            return False
        if multi_site_enabled:
            return True
        return bool(getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True))
