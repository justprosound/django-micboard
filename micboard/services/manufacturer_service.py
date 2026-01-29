"""Manufacturer service base classes and registry.

This module provides the service-oriented architecture for manufacturer integrations,
with direct device lifecycle management and bi-directional sync capabilities.

Architecture:
  ManufacturerService (abstract base)
  ├─ ShureService (concrete implementation)
  ├─ SennheiserService (future)
  └─ ...

  ServiceRegistry (singleton)
  ├─ Register services
  ├─ Lifecycle management
  └─ Configuration overrides

  HardwareLifecycleManager handles all state transitions
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Type

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

logger = logging.getLogger(__name__)


class ManufacturerServiceConfig:
    """Configuration container for a manufacturer service."""

    def __init__(
        self,
        code: str,
        name: str,
        service_class: Type[ManufacturerService],
        enabled: bool = True,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize service configuration.

        Args:
            code: Unique manufacturer code (e.g., 'shure', 'sennheiser')
            name: Display name (e.g., 'Shure Incorporated')
            service_class: Service class to instantiate
            enabled: Whether service is enabled
            config: Configuration overrides
        """
        self.code = code
        self.name = name
        self.service_class = service_class
        self.enabled = enabled
        self.config = config or {}
        self.created_at = timezone.now()

    def __repr__(self) -> str:
        """Return a concise representation showing code, name, and status."""
        status = "enabled" if self.enabled else "disabled"
        return f"<ManufacturerServiceConfig {self.code}: {self.name} ({status})>"


class ManufacturerService(ABC):
    """Abstract base service for manufacturer integrations.

    Services handle:
    - API communication
    - Device discovery and polling
    - Configuration management
    - Signal emission for lifecycle events
    - Error handling and health monitoring

    Subclasses must implement:
    - get_client(): Return configured API client
    - poll_devices(): Fetch devices from API
    - transform_device_data(): Convert API data to standard format
    """

    # Class-level configuration - subclasses must override
    MANUFACTURER_CODE: ClassVar[str]
    MANUFACTURER_NAME: ClassVar[str]
    DEFAULT_POLL_INTERVAL: ClassVar[int] = 30  # seconds
    SUPPORTS_DISCOVERY: ClassVar[bool] = True

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the service.

        Args:
            config: Configuration overrides from admin/settings
        """
        if not self.MANUFACTURER_CODE:
            raise ImproperlyConfigured(f"{self.__class__.__name__} must define MANUFACTURER_CODE")

        self.config = config or {}
        self._client = None
        self._last_poll: Optional[datetime] = None
        self._last_health_check: Optional[datetime] = None
        self._is_healthy = False
        self._error_count = 0
        self._poll_count = 0

        # Initialize lifecycle manager for this service
        from micboard.services.hardware_lifecycle import get_lifecycle_manager

        self._lifecycle_manager = get_lifecycle_manager(service_code=self.code)

        logger.info(
            f"Initialized service: {self.name} ({self.code})",
            extra={
                "service": self.code,
                "config_keys": list(self.config.keys()),
            },
        )

    @property
    def code(self) -> str:
        """Return manufacturer code."""
        return self.MANUFACTURER_CODE

    @property
    def name(self) -> str:
        """Return manufacturer name."""
        return self.MANUFACTURER_NAME

    @property
    def last_poll(self) -> Optional[datetime]:
        """Get timestamp of last successful poll."""
        return self._last_poll

    @property
    def is_healthy(self) -> bool:
        """Get current health status."""
        return self._is_healthy

    @property
    def error_count(self) -> int:
        """Get count of recent errors."""
        return self._error_count

    @property
    def poll_count(self) -> int:
        """Get count of successful polls."""
        return self._poll_count

    @abstractmethod
    def get_client(self) -> Any:
        """Get or create the API client.

        Returns:
            Configured API client instance
        """
        raise NotImplementedError()

    def check_health(self) -> Dict[str, Any]:
        """Check service health.

        Returns:
            Dict with keys:
            - status: 'healthy', 'degraded', or 'unhealthy'
            - is_healthy: boolean
            - message: human-readable status
            - last_poll: timestamp of last successful poll
            - error_count: recent error count
            - poll_count: successful poll count
            - timestamp: check timestamp
        """
        self._last_health_check = timezone.now()

        try:
            client = self.get_client()
            if not client:
                self._is_healthy = False
                return {
                    "status": "unhealthy",
                    "is_healthy": False,
                    "message": "Client initialization failed",
                    "timestamp": self._last_health_check,
                }

            # Client-specific health check
            client_health = client.check_health()

            self._is_healthy = client_health.get("status") == "healthy"
            self._error_count = max(0, self._error_count - 1)  # Decay error count

            status = "healthy" if self._is_healthy else "degraded"
            message = client_health.get("message", "OK")

            return {
                "status": status,
                "is_healthy": self._is_healthy,
                "message": message,
                "last_poll": self._last_poll,
                "error_count": self._error_count,
                "poll_count": self._poll_count,
                "timestamp": self._last_health_check,
            }

        except Exception as e:
            self._is_healthy = False
            self._error_count += 1
            logger.error(
                f"Health check failed for {self.code}: {e}",
                exc_info=True,
                extra={"service": self.code},
            )
            return {
                "status": "unhealthy",
                "is_healthy": False,
                "message": str(e),
                "error_count": self._error_count,
                "timestamp": timezone.now(),
            }

    @abstractmethod
    def poll_devices(self) -> List[Dict[str, Any]]:
        """Poll the manufacturer API for devices.

        Should:
        1. Fetch devices from API
        2. Transform to standard format
        3. Emit appropriate signals
        4. Handle errors gracefully

        Returns:
            List of device dicts in standard format
        """
        raise NotImplementedError()

    @abstractmethod
    def get_device_details(self, device_id: str) -> Dict[str, Any]:
        """Fetch detailed information for a specific device.

        Args:
            device_id: Device identifier from API

        Returns:
            Device details dict in standard format
        """
        raise NotImplementedError()

    @abstractmethod
    def transform_device_data(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform manufacturer API data to standard format.

        Standard format:
        {
            'id': str,
            'model': str,
            'ip': str,
            'state': str (ONLINE/OFFLINE/DISCOVERING),
            'firmware_version': str,
            'serial_number': str,
            'properties': dict,
        }

        Args:
            api_data: Raw data from manufacturer API

        Returns:
            Transformed device data
        """
        raise NotImplementedError()

    def configure_discovery(self, ips: List[str]) -> bool:
        """Configure IP addresses for discovery (if supported).

        Args:
            ips: List of IP addresses to discover

        Returns:
            True if configuration succeeded, False otherwise
        """
        if not self.SUPPORTS_DISCOVERY:
            logger.warning(f"{self.name} does not support discovery configuration")
            return False

        logger.info(
            f"Configuring discovery for {self.code} with {len(ips)} IPs",
            extra={"service": self.code, "ip_count": len(ips)},
        )
        return True

    # Device lifecycle methods (use HardwareLifecycleManager directly)

    def update_device_from_api(
        self,
        device,
        api_data: Dict[str, Any],
    ) -> bool:
        """Update device from API data (pull sync).

        Args:
            device: WirelessChassis or WirelessUnit instance
            api_data: Raw data from manufacturer API

        Returns:
            True if update succeeded
        """
        return self._lifecycle_manager.update_device_from_api(
            device, api_data, service_code=self.code
        )

    def sync_device_to_api(
        self,
        device,
        *,
        fields: Optional[List[str]] = None,
    ) -> bool:
        """Push device changes to API (push sync).

        Args:
            device: Device to sync
            fields: Optional list of fields to sync

        Returns:
            True if sync succeeded
        """
        return self._lifecycle_manager.sync_device_to_api(device, self, fields=fields)

    def mark_hardware_online(self, device, *, health_data: Optional[Dict[str, Any]] = None) -> bool:
        """Mark device as online."""
        success = self._lifecycle_manager.mark_online(device, health_data=health_data)
        if success:
            self._emit_status_changed(device)
        return success

    def mark_hardware_offline(self, device, *, reason: str = "Not responding") -> bool:
        """Mark device as offline."""
        success = self._lifecycle_manager.mark_offline(device, reason=reason)
        if success:
            self._emit_status_changed(device)
        return success

    def mark_device_degraded(self, device, *, warnings: Optional[List[str]] = None) -> bool:
        """Mark device as degraded."""
        success = self._lifecycle_manager.mark_degraded(device, warnings=warnings)
        if success:
            self._emit_status_changed(device)
        return success

    def check_device_health(self, device, *, threshold_minutes: int = 5) -> str:
        """Check device health and auto-transition if needed."""
        return self._lifecycle_manager.check_device_health(
            device, threshold_minutes=threshold_minutes
        )

    def bulk_health_check(self, devices: List, *, threshold_minutes: int = 5) -> Dict[str, int]:
        """Check health of multiple devices."""
        return self._lifecycle_manager.bulk_health_check(
            devices, threshold_minutes=threshold_minutes
        )

    # Minimal signal emission for UI updates

    def _emit_status_changed(self, device) -> None:
        """Broadcast status change via service (replacing signals)."""
        try:
            from channels.layers import get_channel_layer

            if not get_channel_layer():
                return
            from micboard.services.broadcast_service import BroadcastService

            is_online = getattr(device, "is_online", device.status == "online")
            BroadcastService.broadcast_device_status(
                service_code=self.code,
                device_id=device.pk,
                device_type=device.__class__.__name__,
                status=device.status,
                is_active=is_online,
            )
        except ImportError:
            pass

    def emit_sync_complete(self, sync_result: Dict[str, Any]) -> None:
        """Broadcast sync completion via service (replacing signals)."""
        logger.info(
            f"Sync complete for {self.code}",
            extra={"service": self.code, "sync_result": sync_result},
        )
        try:
            from channels.layers import get_channel_layer

            if not get_channel_layer():
                return
            from micboard.services.broadcast_service import BroadcastService

            BroadcastService.broadcast_sync_completion(
                service_code=self.code,
                sync_result=sync_result,
            )
        except ImportError:
            pass


class ServiceRegistry:
    """Registry for all manufacturer services.

    Provides:
    - Singleton management
    - Service discovery
    - Configuration override
    - Lifecycle management
    """

    def __init__(self):
        """Initialize service and configuration registries."""
        self._services: Dict[str, ManufacturerService] = {}
        self._configs: Dict[str, ManufacturerServiceConfig] = {}

    def register(self, config: ManufacturerServiceConfig) -> None:
        """Register a manufacturer service."""
        if config.code in self._configs:
            logger.warning(
                f"Overriding service config for {config.code}",
                extra={"code": config.code},
            )

        self._configs[config.code] = config
        logger.info(
            f"Registered service: {config.name} ({config.code})",
            extra={"code": config.code, "name": config.name},
        )

    def get_service(self, code: str) -> Optional[ManufacturerService]:
        """Get or create a service instance."""
        if code not in self._services:
            if code not in self._configs:
                logger.error(f"Service not registered: {code}", extra={"code": code})
                return None

            config = self._configs[code]
            if not config.enabled:
                logger.warning(
                    f"Service disabled: {code}",
                    extra={"code": code},
                )
                return None

            try:
                self._services[code] = config.service_class(config=config.config)
                logger.info(
                    f"Initialized service instance: {code}",
                    extra={"code": code},
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize service {code}: {e}",
                    exc_info=True,
                    extra={"code": code},
                )
                return None

        return self._services[code]

    def get_all_services(self) -> List[ManufacturerService]:
        """Get all registered and enabled service instances."""
        services = []
        for code in self._configs:
            if self._configs[code].enabled:
                service = self.get_service(code)
                if service:
                    services.append(service)
        return services

    def list_registered(self) -> List[ManufacturerServiceConfig]:
        """List all registered service configs."""
        return list(self._configs.values())

    def reload_config(self, code: str, config: Dict[str, Any]) -> None:
        """Reload service config from admin/database."""
        logger.info(
            f"Reloading config for {code}",
            extra={"code": code},
        )

        if code in self._services:
            del self._services[code]  # Force re-initialization

        if code in self._configs:
            self._configs[code].config = config

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all services."""
        return {service.code: service.check_health() for service in self.get_all_services()}

    def unregister(self, code: str) -> None:
        """Unregister a service."""
        if code in self._services:
            del self._services[code]
        if code in self._configs:
            del self._configs[code]
        logger.info(f"Unregistered service: {code}", extra={"code": code})


# Global service registry singleton
_service_registry = ServiceRegistry()


def register_service(config: ManufacturerServiceConfig) -> None:
    """Register a manufacturer service in the global registry."""
    _service_registry.register(config)


def get_service(code: str) -> Optional[ManufacturerService]:
    """Get a manufacturer service from the global registry."""
    return _service_registry.get_service(code)


def get_all_services() -> List[ManufacturerService]:
    """Get all registered and enabled services."""
    return _service_registry.get_all_services()


def list_registered_services() -> List[ManufacturerServiceConfig]:
    """List all registered service configs."""
    return _service_registry.list_registered()


def get_service_registry() -> ServiceRegistry:
    """Get the global service registry."""
    return _service_registry
