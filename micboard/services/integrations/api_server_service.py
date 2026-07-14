"""Secure connectivity checks for persisted manufacturer API servers."""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from micboard.models.integrations import ManufacturerAPIServer

logger = logging.getLogger(__name__)


def sanitized_api_exception_info(
    exc: Exception,
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    """Return traceback context whose rendered exception cannot expose credentials."""
    safe_exception = RuntimeError(f"{type(exc).__name__}: API error details redacted")
    return RuntimeError, safe_exception, exc.__traceback__


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
                exc_info=sanitized_api_exception_info(exc),
            )
            server.status = ManufacturerAPIServer.Status.ERROR
            server.status_message = f"Connection failed ({type(exc).__name__})"
            server.last_health_check = timezone.now()
            server.save(
                update_fields=["status", "status_message", "last_health_check", "updated_at"]
            )
