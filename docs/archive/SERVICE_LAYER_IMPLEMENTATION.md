# Service Layer Implementation Guide - Phase 2.1

## Quick Start: Service Layer Refactoring

This guide provides step-by-step implementation for django-micboard's service layer, replacing Django signals with explicit services.

---

## Step 1: Core Service Infrastructure (Days 1-2)

### 1.1 Create Service Contracts Module

**File**: `micboard/services/__init__.py` (NEW)
```python
"""Services package for django-micboard."""
from __future__ import annotations

from .contracts import (
    ServiceResult,
    DeviceServiceContract,
    SynchronizationServiceContract,
)
from .device import DeviceService
from .synchronization import SynchronizationService

__all__ = [
    'ServiceResult',
    'DeviceServiceContract',
    'SynchronizationServiceContract',
    'DeviceService',
    'SynchronizationService',
]
```

**File**: `micboard/services/contracts.py` (NEW)
```python
"""Service layer contracts and interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

class ServiceStatus(Enum):
    """Service operation status."""
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"
    PARTIAL = "partial"

@dataclass
class ServiceResult:
    """
    Standard result container for service operations.

    Attributes:
        status: Operation status (success, failure, warning, partial)
        data: Operation result data
        error: Error message if failed
        warnings: List of warning messages
        metadata: Additional operation metadata
    """
    status: ServiceStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True if operation succeeded."""
        return self.status in (ServiceStatus.SUCCESS, ServiceStatus.PARTIAL)

    @property
    def failed(self) -> bool:
        """True if operation failed."""
        return self.status == ServiceStatus.FAILURE

class DeviceServiceContract(ABC):
    """Contract for device-related operations."""

    @abstractmethod
    def get_device(self, device_id: str) -> ServiceResult:
        """Get device by ID."""
        pass

    @abstractmethod
    def update_device_state(
        self,
        device_id: str,
        *,
        battery_level: Optional[int] = None,
        signal_strength: Optional[int] = None,
        is_online: Optional[bool] = None,
    ) -> ServiceResult:
        """Update device state."""
        pass

    @abstractmethod
    def get_device_status(self, device_id: str) -> ServiceResult:
        """Get current device status."""
        pass

class SynchronizationServiceContract(ABC):
    """Contract for device synchronization."""

    @abstractmethod
    def sync_device(
        self,
        manufacturer_code: str,
        device_id: str,
    ) -> ServiceResult:
        """Synchronize single device with manufacturer."""
        pass

    @abstractmethod
    def sync_all_devices(self, manufacturer_code: str) -> ServiceResult:
        """Synchronize all devices for manufacturer."""
        pass
```

### 1.2 Create Device Service

**File**: `micboard/services/device.py` (NEW)
```python
"""Device management service."""
from __future__ import annotations

import logging
from typing import Optional

from django.core.cache import cache
from django.db import transaction

from micboard.models import Device, Receiver, Transmitter, Manufacturer
from micboard.exceptions import DeviceNotFound, DeviceValidationError

from .contracts import DeviceServiceContract, ServiceResult, ServiceStatus

logger = logging.getLogger(__name__)

class DeviceService(DeviceServiceContract):
    """Service for device operations."""

    def __init__(self):
        """Initialize service."""
        self.cache_ttl = 300  # 5 minutes

    def get_device(self, device_id: str) -> ServiceResult:
        """
        Get device by ID.

        Returns:
            ServiceResult with device data
        """
        try:
            device = Device.objects.select_related(
                'manufacturer',
                'location',
            ).get(device_id=device_id)

            return ServiceResult(
                status=ServiceStatus.SUCCESS,
                data={
                    'id': device.id,
                    'device_id': device.device_id,
                    'name': device.name,
                    'is_online': device.is_online,
                    'battery_level': device.battery_level,
                    'signal_strength': device.signal_strength,
                },
            )
        except Device.DoesNotExist:
            logger.warning(f"Device not found: {device_id}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=f"Device '{device_id}' not found",
            )
        except Exception as e:
            logger.exception(f"Error getting device: {device_id}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=str(e),
            )

    @transaction.atomic
    def update_device_state(
        self,
        device_id: str,
        *,
        battery_level: Optional[int] = None,
        signal_strength: Optional[int] = None,
        is_online: Optional[bool] = None,
    ) -> ServiceResult:
        """
        Update device state with validation.

        Args:
            device_id: Device identifier
            battery_level: Battery level 0-100 (optional)
            signal_strength: Signal in dBm (optional)
            is_online: Online status (optional)

        Returns:
            ServiceResult with update status
        """
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=f"Device '{device_id}' not found",
            )

        # Validate inputs
        try:
            if battery_level is not None:
                if not (0 <= battery_level <= 100):
                    return ServiceResult(
                        status=ServiceStatus.FAILURE,
                        error=f"Battery level must be 0-100, got {battery_level}",
                    )
                device.battery_level = battery_level

            if signal_strength is not None:
                if not (-100 <= signal_strength <= 0):
                    return ServiceResult(
                        status=ServiceStatus.FAILURE,
                        error=f"Signal strength must be -100 to 0 dBm",
                    )
                device.signal_strength = signal_strength

            if is_online is not None:
                device.is_online = is_online
        except Exception as e:
            logger.exception(f"Validation error for {device_id}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=f"Validation failed: {str(e)}",
            )

        try:
            device.save(update_fields=['battery_level', 'signal_strength', 'is_online'])

            # Update cache
            cache.set(
                f'device:{device_id}',
                {
                    'battery': device.battery_level,
                    'signal': device.signal_strength,
                    'online': device.is_online,
                },
                self.cache_ttl,
            )

            logger.info(f"Device {device_id} state updated")

            return ServiceResult(
                status=ServiceStatus.SUCCESS,
                data={'device_id': device_id},
            )
        except Exception as e:
            logger.exception(f"Error updating device {device_id}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=str(e),
            )

    def get_device_status(self, device_id: str) -> ServiceResult:
        """Get current device status without synchronization."""
        try:
            device = Device.objects.get(device_id=device_id)

            return ServiceResult(
                status=ServiceStatus.SUCCESS,
                data={
                    'device_id': device_id,
                    'is_online': device.is_online,
                    'battery_level': device.battery_level,
                    'signal_strength': device.signal_strength,
                    'last_seen': device.last_updated.isoformat() if device.last_updated else None,
                },
            )
        except Exception as e:
            logger.exception(f"Error getting status for {device_id}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=str(e),
            )

    def notify_device_update(self, device: Device) -> None:
        """
        Explicit notification after device update.

        Caller controls when/if this happens (no signals).
        """
        # Update cache
        cache.set(
            f'device:{device.device_id}',
            {
                'battery': device.battery_level,
                'signal': device.signal_strength,
                'online': device.is_online,
            },
            self.cache_ttl,
        )

        # Broadcast WebSocket update (if needed)
        try:
            from micboard.websockets.broadcaster import broadcast_device_update
            broadcast_device_update(device)
        except ImportError:
            # WebSocket module not available
            pass

        logger.debug(f"Device {device.device_id} notification sent")
```

### 1.3 Create Synchronization Service

**File**: `micboard/services/synchronization.py` (NEW)
```python
"""Device synchronization service."""
from __future__ import annotations

import logging
from typing import Dict, Any

from django.core.cache import cache
from django.db import transaction

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Device, Manufacturer
from micboard.exceptions import ManufacturerNotSupported, APIError

from .contracts import SynchronizationServiceContract, ServiceResult, ServiceStatus

logger = logging.getLogger(__name__)

class SynchronizationService(SynchronizationServiceContract):
    """Service for device synchronization with manufacturers."""

    def sync_device(
        self,
        manufacturer_code: str,
        device_id: str,
    ) -> ServiceResult:
        """
        Synchronize single device with manufacturer API.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure')
            device_id: Device ID from manufacturer

        Returns:
            ServiceResult with sync status
        """
        try:
            # Get manufacturer plugin
            plugin = get_manufacturer_plugin(manufacturer_code)

            # Fetch from manufacturer API
            remote_data = plugin.get_device(device_id)
            if not remote_data:
                return ServiceResult(
                    status=ServiceStatus.FAILURE,
                    error=f"Device not found on manufacturer API: {device_id}",
                )

            # Get or create device in database
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
            device, created = Device.objects.get_or_create(
                device_id=device_id,
                manufacturer=manufacturer,
            )

            # Update from remote data
            device.update_from_remote(remote_data)
            device.save()

            # Update cache
            cache.set(
                f'device:{device_id}',
                remote_data,
                300,  # 5 minutes
            )

            logger.info(
                f"Device synced: {device_id} ({'created' if created else 'updated'})"
            )

            return ServiceResult(
                status=ServiceStatus.SUCCESS,
                data={
                    'device_id': device_id,
                    'created': created,
                    'battery': device.battery_level,
                    'signal': device.signal_strength,
                },
            )

        except ManufacturerNotSupported as e:
            logger.error(f"Manufacturer not supported: {manufacturer_code}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=str(e),
            )
        except APIError as e:
            logger.error(f"API error syncing {device_id}: {str(e)}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=f"API error: {str(e)}",
            )
        except Exception as e:
            logger.exception(f"Error syncing device {device_id}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=str(e),
            )

    @transaction.atomic
    def sync_all_devices(self, manufacturer_code: str) -> ServiceResult:
        """
        Synchronize all devices for a manufacturer.

        Returns:
            ServiceResult with batch sync status
        """
        try:
            plugin = get_manufacturer_plugin(manufacturer_code)
            devices = plugin.get_devices()

            synced = 0
            failed = 0
            warnings = []

            for device_data in devices:
                device_id = device_data.get('id')
                result = self.sync_device(manufacturer_code, device_id)

                if result.success:
                    synced += 1
                else:
                    failed += 1
                    warnings.append(f"{device_id}: {result.error}")

            return ServiceResult(
                status=ServiceStatus.PARTIAL if failed > 0 else ServiceStatus.SUCCESS,
                data={
                    'synced': synced,
                    'failed': failed,
                    'total': synced + failed,
                },
                warnings=warnings[:10],  # Limit warnings
            )

        except Exception as e:
            logger.exception(f"Error syncing all devices for {manufacturer_code}")
            return ServiceResult(
                status=ServiceStatus.FAILURE,
                error=str(e),
            )
```

---

## Step 2: Exceptions Module (Days 3)

**File**: `micboard/exceptions.py` (NEW)
```python
"""Custom exceptions for django-micboard."""
from __future__ import annotations

from typing import Optional, Dict, Any

class MicboardException(Exception):
    """Base exception for all micboard errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

class ManufacturerNotSupported(MicboardException):
    """Raised when manufacturer is not supported."""

    def __init__(self, manufacturer_code: str):
        super().__init__(
            f"Manufacturer '{manufacturer_code}' is not supported",
            code="MANUFACTURER_NOT_SUPPORTED",
            details={'manufacturer': manufacturer_code},
        )

class DeviceNotFound(MicboardException):
    """Raised when device is not found."""

    def __init__(self, device_id: str):
        super().__init__(
            f"Device '{device_id}' not found",
            code="DEVICE_NOT_FOUND",
            details={'device_id': device_id},
        )

class DeviceValidationError(MicboardException):
    """Raised when device data is invalid."""

    def __init__(self, field: str, message: str):
        super().__init__(
            f"Validation error on {field}: {message}",
            code="DEVICE_VALIDATION_ERROR",
            details={'field': field, 'message': message},
        )

class APIError(MicboardException):
    """Raised when manufacturer API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(
            message,
            code="API_ERROR",
            details={'status_code': status_code, 'response': response_body},
        )

class LocationNotFound(MicboardException):
    """Raised when location is not found."""

    def __init__(self, location_id: int):
        super().__init__(
            f"Location with ID {location_id} not found",
            code="LOCATION_NOT_FOUND",
            details={'location_id': location_id},
        )
```

---

## Step 3: Usage Examples (Days 4-5)

### 3.1 In API Views

**File**: `micboard/api/viewsets.py` (UPDATE - Example)
```python
"""REST API viewsets."""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from micboard.models import Device
from micboard.services import DeviceService, SynchronizationService

class ReceiverViewSet(viewsets.ReadOnlyModelViewSet):
    """Receiver management viewset."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_service = DeviceService()
        self.sync_service = SynchronizationService()

    @action(detail=False, methods=['post'])
    def sync(self, request):
        """Synchronize devices for manufacturer."""
        manufacturer_code = request.data.get('manufacturer')

        result = self.sync_service.sync_all_devices(manufacturer_code)

        if result.success:
            return Response(result.data, status=200)
        else:
            return Response({'error': result.error}, status=400)

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get device status."""
        device = self.get_object()
        result = self.device_service.get_device_status(device.device_id)

        return Response(result.data, status=200)
```

### 3.2 In Management Commands

**File**: `micboard/management/commands/poll_devices.py` (UPDATE - Example)
```python
"""Management command for device polling."""
from django.core.management.base import BaseCommand

from micboard.services import SynchronizationService
from micboard.models import Manufacturer

class Command(BaseCommand):
    """Poll all devices from manufacturer APIs."""

    help = 'Synchronize devices with manufacturer APIs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--manufacturer',
            type=str,
            help='Specific manufacturer to sync',
        )

    def handle(self, *args, **options):
        """Execute polling."""
        service = SynchronizationService()

        if options['manufacturer']:
            manufacturers = Manufacturer.objects.filter(
                code=options['manufacturer']
            )
        else:
            manufacturers = Manufacturer.objects.filter(is_active=True)

        for manufacturer in manufacturers:
            self.stdout.write(f"Syncing {manufacturer.name}...")

            result = service.sync_all_devices(manufacturer.code)

            if result.success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Synced {result.data['synced']} devices"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ Error: {result.error}")
                )
```

---

## Step 4: Remove Signals (Days 6-7)

### 4.1 Audit Current Signals

```bash
# Find all signal handlers
grep -r "@receiver" micboard/ --include="*.py"
grep -r "post_save\|post_delete\|pre_save" micboard/ --include="*.py"
```

### 4.2 Replace Each Signal with Service Call

**BEFORE** (Signal):
```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Device)
def device_saved(sender, instance, **kwargs):
    cache.set(f'device:{instance.id}', serialize_device(instance))
    notify_websocket(instance)
```

**AFTER** (Service):
```python
# In your view or command
from micboard.services import DeviceService

service = DeviceService()
result = service.update_device_state(device_id, battery_level=85)
if result.success:
    device = Device.objects.get(device_id=device_id)
    service.notify_device_update(device)  # Explicit notification
```

---

## Step 5: Tests (Days 8)

**File**: `tests/services/test_device_service.py` (NEW)
```python
"""Tests for DeviceService."""
import pytest
from unittest.mock import Mock, patch

from micboard.services import DeviceService
from micboard.services.contracts import ServiceStatus

@pytest.mark.django_db
class TestDeviceService:
    """Test DeviceService."""

    def test_update_device_state_success(self, receiver):
        """Test successful device update."""
        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=50,
        )

        assert result.status == ServiceStatus.SUCCESS
        receiver.refresh_from_db()
        assert receiver.battery_level == 50

    def test_update_device_invalid_battery(self, receiver):
        """Test validation of battery level."""
        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=150,  # Invalid
        )

        assert result.status == ServiceStatus.FAILURE
        assert "0-100" in result.error

    def test_get_device_not_found(self):
        """Test getting non-existent device."""
        service = DeviceService()
        result = service.get_device("invalid_id")

        assert result.status == ServiceStatus.FAILURE
        assert "not found" in result.error.lower()
```

---

## Verification Checklist

- [ ] Service contracts defined (contracts.py)
- [ ] DeviceService implemented
- [ ] SynchronizationService implemented
- [ ] Exceptions module created
- [ ] Signal handlers audited
- [ ] Replace signals with service calls
- [ ] Update API views to use services
- [ ] Update management commands
- [ ] Service tests written (95%+ coverage)
- [ ] All existing tests passing
- [ ] Documentation updated
- [ ] Code reviewed

---

**Ready to implement?** Start with Step 1!

Next: See PRODUCTION_READINESS_REFACTOR.md for full context.
