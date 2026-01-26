# Phase 2 Implementation Guide - Django Best Practices & Modularization

## Overview

This guide provides step-by-step implementation for Phase 2 refactoring based on PHASE_2_MODULARIZATION.md.

**Timeline**: 8 weeks post v25.01.15
**Target Release**: v25.02.15 (February 15, 2025)
**Coverage Goal**: Maintain 95%+ throughout refactoring

---

## Step 1: Extract Custom Managers (Week 1)

### File: `micboard/models/managers.py` (NEW)

**Goal**: Centralize custom manager logic, reduce model file size, improve reusability.

**Current State**: Managers likely embedded in model classes
**Target State**: Separate file with clean manager classes

```python
"""
Custom managers and querysets for device models.

Provides common filtering, optimization, and related-field handling.
"""
from __future__ import annotations

from django.db import models
from django.db.models import Prefetch, Q


class DeviceQuerySet(models.QuerySet):
    """
    Common queryset methods for device models.

    Provides filtering for online status, battery level, signal strength.
    """

    def active(self):
        """Filter to active devices."""
        return self.filter(is_active=True)

    def online(self):
        """Filter to online devices."""
        return self.filter(is_online=True)

    def offline(self):
        """Filter to offline devices."""
        return self.filter(is_online=False)

    def low_battery(self, threshold: int = 20):
        """
        Filter to devices with battery below threshold.

        Args:
            threshold: Battery percentage (0-100). Default: 20%

        Returns:
            QuerySet: Filtered devices
        """
        return self.filter(battery_level__lt=threshold)

    def good_battery(self, threshold: int = 20):
        """Filter to devices with battery above threshold."""
        return self.filter(battery_level__gte=threshold)

    def weak_signal(self, threshold: int = -80):
        """
        Filter to devices with weak signal.

        Args:
            threshold: Signal strength in dBm. Default: -80 dBm (weak)

        Returns:
            QuerySet: Filtered devices (more negative = weaker)
        """
        return self.filter(signal_strength__lt=threshold)

    def strong_signal(self, threshold: int = -80):
        """Filter to devices with strong signal."""
        return self.filter(signal_strength__gte=threshold)

    def by_manufacturer(self, code: str):
        """Filter to specific manufacturer."""
        return self.filter(manufacturer__code=code)

    def by_location(self, location_id: int | None):
        """Filter to specific location or unassigned if None."""
        if location_id is None:
            return self.filter(location__isnull=True)
        return self.filter(location_id=location_id)

    def with_details(self):
        """
        Optimize queryset with select_related and prefetch_related.

        Reduces N+1 queries for common access patterns.
        """
        return self.select_related(
            'manufacturer',
            'location',
        )


class ReceiverManager(models.Manager):
    """Manager for Receiver model."""

    def get_queryset(self):
        """Return optimized queryset by default."""
        return DeviceQuerySet(self.model).with_details()

    def get_by_device_id(self, device_id: str, manufacturer_code: str):
        """
        Get receiver by device ID and manufacturer.

        Args:
            device_id: Device identifier (e.g., 'rx_0001')
            manufacturer_code: Manufacturer code (e.g., 'shure')

        Returns:
            Receiver instance or None
        """
        return self.filter(
            device_id=device_id,
            manufacturer__code=manufacturer_code,
        ).first()


class TransmitterManager(models.Manager):
    """Manager for Transmitter model."""

    def get_queryset(self):
        """Return optimized queryset by default."""
        return DeviceQuerySet(self.model).with_details()

    def by_location_and_manufacturer(self, location_id: int, manufacturer_code: str):
        """Get transmitters for location and manufacturer."""
        return self.filter(
            location_id=location_id,
            manufacturer__code=manufacturer_code,
        )


class LocationManager(models.Manager):
    """Manager for Location model."""

    def get_queryset(self):
        """Return optimized queryset with prefetches."""
        return super().get_queryset().prefetch_related(
            Prefetch('receiver_set', queryset=models.Model.objects.with_details()),
            Prefetch('transmitter_set', queryset=models.Model.objects.with_details()),
        )

    def with_device_counts(self):
        """
        Annotate locations with device counts.

        Returns:
            QuerySet with annotations: receiver_count, transmitter_count, etc.
        """
        from django.db.models import Count, Q

        return self.annotate(
            receiver_count=Count('receiver_set'),
            transmitter_count=Count('transmitter_set'),
            online_receiver_count=Count(
                'receiver_set',
                filter=Q(receiver_set__is_online=True)
            ),
            low_battery_count=Count(
                'receiver_set',
                filter=Q(receiver_set__battery_level__lt=20)
            ),
        )
```

**Update Models** to use new managers:

```python
# In micboard/models/receiver.py
from .managers import ReceiverManager

class Receiver(Device):
    # ...existing fields...

    objects = ReceiverManager()

    class Meta:
        # ...existing meta...
        # Remove any manager definitions
```

---

## Step 2: Create Utilities Package (Week 1)

### File: `micboard/utils/__init__.py` (NEW)

```python
"""
Utilities package for django-micboard.

Provides validators, caching, constants, and helper functions.
"""
from .validators import *
from .cache import *
from .constants import *
from .serialization import *
```

### File: `micboard/utils/constants.py` (NEW)

```python
"""
Project-wide constants and magic numbers.

Centralizes configuration values for easy adjustment.
"""
from __future__ import annotations

# Device-related constants
DEVICE_ID_PATTERN = r'^[a-z]+_\d{4,}$'
BATTERY_MIN = 0
BATTERY_MAX = 100
BATTERY_LOW_THRESHOLD = 20
BATTERY_CRITICAL_THRESHOLD = 10

# Signal strength (dBm)
SIGNAL_EXCELLENT = -30  # dBm
SIGNAL_GOOD = -60  # dBm
SIGNAL_WEAK = -80  # dBm
SIGNAL_CRITICAL = -100  # dBm

# Polling and sync
DEFAULT_POLL_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_OFFLINE_TIMEOUT = 600  # 10 minutes
DEFAULT_SYNC_TIMEOUT = 30  # 30 seconds per API call

# Caching
DEFAULT_CACHE_TTL = 300  # 5 minutes
CACHE_KEYS = {
    'device': 'device:{manufacturer}:{device_id}',
    'location': 'location:{location_id}',
    'location_devices': 'location_devices:{location_id}',
    'health': 'health:overall',
    'manufacturer': 'manufacturer:{code}',
}

# Rate limiting
DEFAULT_RATE_LIMIT = 120  # requests
DEFAULT_RATE_WINDOW = 60  # seconds

# Manufacturer codes
SUPPORTED_MANUFACTURERS = ['shure', 'sennheiser']
```

### File: `micboard/utils/validators.py` (NEW)

```python
"""
Validation utilities for devices, locations, and configurations.
"""
from __future__ import annotations

import re
from typing import Optional

from django.core.exceptions import ValidationError

from .constants import DEVICE_ID_PATTERN


def validate_device_id(device_id: str) -> bool:
    """
    Validate device ID format.

    Args:
        device_id: Device identifier (e.g., 'rx_0001', 'tx_0002')

    Returns:
        True if valid, False otherwise

    Raises:
        ValidationError: If invalid format
    """
    if not device_id or not isinstance(device_id, str):
        raise ValidationError('Device ID must be a non-empty string')

    if not re.match(DEVICE_ID_PATTERN, device_id):
        raise ValidationError(
            f'Device ID must match pattern: {DEVICE_ID_PATTERN}'
        )

    return True


def validate_ip_address(ip: str) -> bool:
    """
    Validate IPv4 address format.

    Args:
        ip: IP address string (e.g., '192.168.1.100')

    Returns:
        True if valid

    Raises:
        ValidationError: If invalid format
    """
    if not ip or not isinstance(ip, str):
        raise ValidationError('IP address must be a non-empty string')

    # Simple regex validation (not production-grade)
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        raise ValidationError(f'Invalid IP address format: {ip}')

    # Validate octets are 0-255
    try:
        octets = [int(octet) for octet in ip.split('.')]
        if not all(0 <= octet <= 255 for octet in octets):
            raise ValidationError(f'IP octets must be 0-255')
    except ValueError:
        raise ValidationError(f'Invalid IP address: {ip}')

    return True


def validate_battery_level(value: int) -> bool:
    """
    Validate battery level (0-100).

    Args:
        value: Battery percentage

    Returns:
        True if valid

    Raises:
        ValidationError: If out of range
    """
    if not isinstance(value, int):
        raise ValidationError('Battery level must be an integer')

    if not (0 <= value <= 100):
        raise ValidationError(f'Battery level must be 0-100, got {value}')

    return True


def validate_signal_strength(value: int) -> bool:
    """
    Validate signal strength (-100 to 0 dBm).

    Args:
        value: Signal strength in dBm (negative values, typically -100 to -10)

    Returns:
        True if valid

    Raises:
        ValidationError: If out of range
    """
    if not isinstance(value, int):
        raise ValidationError('Signal strength must be an integer')

    if not (-100 <= value <= 0):
        raise ValidationError(f'Signal strength must be -100 to 0 dBm, got {value}')

    return True


def validate_manufacturer_code(code: str) -> bool:
    """
    Validate manufacturer code against supported list.

    Args:
        code: Manufacturer code (e.g., 'shure', 'sennheiser')

    Returns:
        True if valid

    Raises:
        ValidationError: If not supported
    """
    from .constants import SUPPORTED_MANUFACTURERS

    if not code or not isinstance(code, str):
        raise ValidationError('Manufacturer code must be a non-empty string')

    code_lower = code.lower()
    if code_lower not in SUPPORTED_MANUFACTURERS:
        raise ValidationError(
            f'Unsupported manufacturer: {code}. '
            f'Supported: {", ".join(SUPPORTED_MANUFACTURERS)}'
        )

    return True
```

### File: `micboard/utils/cache.py` (NEW)

```python
"""
Cache management utilities.

Provides cache key generation, TTL management, and cache operations.
"""
from __future__ import annotations

from typing import Any, Optional

from django.core.cache import cache as django_cache

from .constants import CACHE_KEYS, DEFAULT_CACHE_TTL


def get_cache_key(key_template: str, **kwargs) -> str:
    """
    Generate cache key from template.

    Args:
        key_template: Template from CACHE_KEYS (e.g., 'device:{manufacturer}:{device_id}')
        **kwargs: Values for template substitution

    Returns:
        Formatted cache key
    """
    return key_template.format(**kwargs)


def get_device_cache_key(manufacturer_code: str, device_id: str) -> str:
    """Get cache key for device."""
    return get_cache_key(CACHE_KEYS['device'], manufacturer=manufacturer_code, device_id=device_id)


def get_location_cache_key(location_id: int) -> str:
    """Get cache key for location."""
    return get_cache_key(CACHE_KEYS['location'], location_id=location_id)


def cache_get(key: str, default: Any = None) -> Any:
    """
    Get value from cache.

    Args:
        key: Cache key
        default: Default value if not found

    Returns:
        Cached value or default
    """
    return django_cache.get(key, default)


def cache_set(key: str, value: Any, timeout: int = DEFAULT_CACHE_TTL) -> None:
    """
    Set value in cache.

    Args:
        key: Cache key
        value: Value to cache
        timeout: TTL in seconds (default: 5 minutes)
    """
    django_cache.set(key, value, timeout)


def cache_delete(key: str) -> None:
    """Delete value from cache."""
    django_cache.delete(key)


def cache_invalidate_pattern(pattern: str) -> None:
    """
    Invalidate all cache keys matching pattern.

    Note: Requires cache backend that supports pattern deletion (Redis, Memcached).

    Args:
        pattern: Pattern with wildcards (e.g., 'device:shure:*')
    """
    django_cache.delete_pattern(pattern)
```

### File: `micboard/utils/serialization.py` (NEW)

```python
"""
Common serialization helpers for models and API responses.
"""
from __future__ import annotations

from typing import Any, Dict, List

from micboard.models import Receiver, Transmitter, Location


def serialize_device_state(device: Receiver | Transmitter) -> Dict[str, Any]:
    """
    Serialize device state for API/WebSocket.

    Args:
        device: Device instance (Receiver or Transmitter)

    Returns:
        Dictionary with device state
    """
    return {
        'id': device.id,
        'device_id': device.device_id,
        'name': device.name,
        'manufacturer': device.manufacturer.code,
        'is_online': device.is_online,
        'battery_level': device.battery_level,
        'signal_strength': device.signal_strength,
        'last_updated': device.last_updated.isoformat() if device.last_updated else None,
    }


def serialize_location_summary(location: Location) -> Dict[str, Any]:
    """
    Serialize location with device summary.

    Args:
        location: Location instance

    Returns:
        Dictionary with location and device counts
    """
    receivers = location.receiver_set.all()
    transmitters = location.transmitter_set.all()

    return {
        'id': location.id,
        'name': location.name,
        'description': location.description,
        'receiver_count': receivers.count(),
        'transmitter_count': transmitters.count(),
        'online_receivers': receivers.filter(is_online=True).count(),
        'low_battery': receivers.filter(battery_level__lt=20).count(),
    }
```

---

## Step 3: Organize Serializers Package (Week 2)

### File: `micboard/serializers/__init__.py` (NEW)

```python
"""
Django REST Framework serializers for django-micboard.

Organized by resource type: receivers, transmitters, locations, health.
"""
from .receivers import ReceiverSerializer, ReceiverDetailSerializer
from .transmitters import TransmitterSerializer
from .locations import LocationSerializer, LocationDetailSerializer
from .health import HealthStatusSerializer

__all__ = [
    'ReceiverSerializer',
    'ReceiverDetailSerializer',
    'TransmitterSerializer',
    'LocationSerializer',
    'LocationDetailSerializer',
    'HealthStatusSerializer',
]
```

### File: `micboard/serializers/base.py` (NEW)

```python
"""
Base serializers with common device fields and methods.
"""
from __future__ import annotations

from rest_framework import serializers

from micboard.models import Manufacturer, Location


class BaseDeviceSerializer(serializers.ModelSerializer):
    """
    Base serializer for device models (Receiver, Transmitter).

    Includes common fields: manufacturer, location, state, timestamps.
    """
    manufacturer_name = serializers.CharField(
        source='manufacturer.name',
        read_only=True
    )
    location_name = serializers.CharField(
        source='location.name',
        read_only=True,
        allow_null=True
    )
    battery_level_percentage = serializers.SerializerMethodField()
    signal_quality = serializers.SerializerMethodField()

    def get_battery_level_percentage(self, obj) -> str:
        """Return human-readable battery level."""
        if obj.battery_level is None:
            return 'unknown'
        if obj.battery_level < 10:
            return 'critical'
        if obj.battery_level < 20:
            return 'low'
        return 'good'

    def get_signal_quality(self, obj) -> str:
        """Return human-readable signal quality."""
        if obj.signal_strength is None:
            return 'unknown'
        if obj.signal_strength < -100:
            return 'no_signal'
        if obj.signal_strength < -80:
            return 'weak'
        if obj.signal_strength < -60:
            return 'fair'
        return 'excellent'

    class Meta:
        fields = [
            'id',
            'device_id',
            'name',
            'manufacturer',
            'manufacturer_name',
            'location',
            'location_name',
            'is_online',
            'battery_level',
            'battery_level_percentage',
            'signal_strength',
            'signal_quality',
            'last_updated',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'last_updated',
            'manufacturer_name',
            'location_name',
            'battery_level_percentage',
            'signal_quality',
        ]
```

### File: `micboard/serializers/receivers.py` (NEW)

```python
"""Receiver-specific serializers."""
from __future__ import annotations

from rest_framework import serializers

from micboard.models import Receiver
from .base import BaseDeviceSerializer


class ReceiverSerializer(BaseDeviceSerializer):
    """
    Serializer for Receiver list/detail endpoints.

    Includes all common device fields from BaseDeviceSerializer.
    """
    class Meta(BaseDeviceSerializer.Meta):
        model = Receiver


class ReceiverDetailSerializer(ReceiverSerializer):
    """
    Extended serializer for receiver detail view.

    Includes additional fields not shown in list view.
    """
    class Meta(ReceiverSerializer.Meta):
        fields = ReceiverSerializer.Meta.fields + [
            'ip_address',
            'description',
        ]
```

---

## Step 4: Create API ViewSets (Week 2)

### File: `micboard/api/__init__.py` (NEW)

```python
"""
REST API package for django-micboard.

Provides ViewSets, permissions, filters, and pagination.
"""
```

### File: `micboard/api/viewsets.py` (NEW)

```python
"""
ViewSets for REST API resources.

Each ViewSet provides CRUD operations via DRF's ModelViewSet.
"""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from micboard.models import Receiver, Transmitter, Location
from micboard.serializers import (
    ReceiverSerializer,
    ReceiverDetailSerializer,
    TransmitterSerializer,
    LocationSerializer,
)
from .permissions import IsDeviceAdmin
from .filters import ReceiverFilter


class ReceiverViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Receiver model.

    List: GET /api/receivers/
    Detail: GET /api/receivers/{id}/
    Filtering: /api/receivers/?manufacturer=shure&location=stage1
    """
    queryset = Receiver.objects.all()
    serializer_class = ReceiverSerializer
    filterset_class = ReceiverFilter
    permission_classes = [IsDeviceAdmin]

    def get_serializer_class(self):
        """Use detail serializer for retrieve action."""
        if self.action == 'retrieve':
            return ReceiverDetailSerializer
        return ReceiverSerializer

    @action(detail=False, methods=['get'])
    def low_battery(self, request):
        """Get receivers with low battery."""
        threshold = request.query_params.get('threshold', 20)
        receivers = self.queryset.low_battery(int(threshold))
        serializer = self.get_serializer(receivers, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def offline(self, request):
        """Get offline receivers."""
        receivers = self.queryset.offline()
        serializer = self.get_serializer(receivers, many=True)
        return Response(serializer.data)


class TransmitterViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Transmitter model."""
    queryset = Transmitter.objects.all()
    serializer_class = TransmitterSerializer
    permission_classes = [IsDeviceAdmin]


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Location model."""
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsDeviceAdmin]

    @action(detail=True, methods=['get'])
    def devices(self, request, pk=None):
        """Get all devices in a location."""
        location = self.get_object()
        receivers = location.receiver_set.all()
        serializer = ReceiverSerializer(receivers, many=True)
        return Response(serializer.data)
```

---

## Summary Checklist

### Week 1
- [ ] Create `micboard/models/managers.py`
- [ ] Update models to use new managers
- [ ] Create `micboard/utils/` package
  - [ ] `__init__.py`
  - [ ] `constants.py`
  - [ ] `validators.py`
  - [ ] `cache.py`
  - [ ] `serialization.py`
- [ ] Write unit tests for managers and utils
- [ ] Run full test suite (target: 95%+ coverage)

### Week 2
- [ ] Create `micboard/serializers/` package
  - [ ] `__init__.py`
  - [ ] `base.py`
  - [ ] `receivers.py`
  - [ ] `transmitters.py`
  - [ ] `locations.py`
- [ ] Create `micboard/api/` package
  - [ ] `__init__.py`
  - [ ] `viewsets.py`
  - [ ] `permissions.py` (in next section)
  - [ ] `filters.py` (in next section)
- [ ] Write ViewSet tests
- [ ] Update URL routing
- [ ] Run full test suite

**Progress**: Week 1-2 complete ✅
**Next**: Weeks 3-4 (Views & Permissions)

---

For next sections, see PHASE_2_MODULARIZATION.md for:
- Step 5: URL Routing with include()
- Step 6: Permissions & Access Control
- Step 7: WebSocket Organization
- Step 8: Background Tasks
- Step 9: Testing Module Expansion
