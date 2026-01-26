
# Services Layer Best Practices

## Principle 1: Keyword-Only Parameters

All service methods should use keyword-only parameters to enforce clarity at call sites.

```python
# ✅ Good: Required parameters are explicit
def create_assignment(
    *,
    user: User,
    device: Receiver | Transmitter,
    *,
    alert_enabled: bool = True,
    notes: str = ""
) -> Assignment:
    pass

# Usage is clear and self-documenting
assignment = AssignmentService.create_assignment(
    user=user,
    device=device,
    alert_enabled=True,
    notes="Main stage"
)
```

```python
# ❌ Bad: Positional parameters are ambiguous
def create_assignment(user, device, alert_enabled=True, notes=""):
    pass

# Usage is unclear
assignment = AssignmentService.create_assignment(user, device, True, "Main stage")
```

## Principle 2: Single Responsibility

Each service class should have a single, well-defined domain responsibility.

```python
# ✅ Good: Clear domain responsibility
class DeviceService:
    """Manages device lifecycle and status."""
    # All methods relate to device operations

class AssignmentService:
    """Manages user-device assignments."""
    # All methods relate to assignments

class LocationService:
    """Manages locations."""
    # All methods relate to locations
```

```python
# ❌ Bad: Mixed responsibilities
class AdminService:
    """Does everything."""
    def get_devices(self): ...
    def create_assignment(self): ...
    def delete_location(self): ...
    def sync_from_api(self): ...
    # Too broad!
```

## Principle 3: Return Domain Objects, Not Serialized Data

Services return model instances or DTOs, not JSON or serialized representations.
Serialization is the responsibility of views/API layer.

```python
# ✅ Good: Return model instance
@staticmethod
def get_active_receivers() -> QuerySet:
    return Receiver.objects.filter(active=True)

# In view:
receivers = DeviceService.get_active_receivers()
serializer = ReceiverSerializer(receivers, many=True)
return Response(serializer.data)
```

```python
# ❌ Bad: Serialization in service
@staticmethod
def get_active_receivers() -> list[dict]:
    receivers = Receiver.objects.filter(active=True)
    return [
        {
            'id': r.id,
            'name': r.name,
            'online': r.online
        }
        for r in receivers
    ]  # This is serializer work!
```

## Principle 4: Explicit Error Handling

Services should raise clear, domain-specific exceptions for error conditions.

```python
# ✅ Good: Raise specific exceptions
from micboard.services import AssignmentAlreadyExistsError

@staticmethod
def create_assignment(
    *,
    user: User,
    device: Receiver | Transmitter
) -> Assignment:
    if Assignment.objects.filter(user=user, device_id=device.id).exists():
        raise AssignmentAlreadyExistsError(user_id=user.id, device_id=device.id)

    return Assignment.objects.create(user=user, device_id=device.id)

# In view:
try:
    assignment = AssignmentService.create_assignment(user=user, device=device)
except AssignmentAlreadyExistsError as e:
    return Response({'error': str(e)}, status=400)
```

```python
# ❌ Bad: Generic or no exception
@staticmethod
def create_assignment(user: User, device) -> Assignment | None:
    if Assignment.objects.filter(user=user, device_id=device.id).exists():
        return None  # Ambiguous: what does None mean?

    return Assignment.objects.create(user=user, device_id=device.id)
```

## Principle 5: Type Hints Everywhere

All parameters and return values should have type hints.

```python
# ✅ Good: Complete type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micboard.models import Receiver

@staticmethod
def sync_device_status(
    *,
    device_obj: Receiver,
    *,
    online: bool
) -> None:
    """Update device online status."""
    pass
```

```python
# ❌ Bad: Missing type hints
@staticmethod
def sync_device_status(device_obj, online):
    """Update device online status."""
    pass
```

## Principle 6: Stateless Service Methods

All service methods should be static and not rely on instance state.
This ensures services can be used anywhere without instantiation.

```python
# ✅ Good: Stateless static methods
class DeviceService:
    @staticmethod
    def get_active_receivers() -> QuerySet:
        return Receiver.objects.filter(active=True)

# Usage (no instantiation needed)
receivers = DeviceService.get_active_receivers()
```

```python
# ❌ Bad: Stateful service
class DeviceService:
    def __init__(self):
        self.cache = {}

    def get_active_receivers(self) -> list:
        if 'receivers' not in self.cache:
            self.cache['receivers'] = Receiver.objects.filter(active=True)
        return self.cache['receivers']

# Usage requires instantiation
service = DeviceService()
receivers = service.get_active_receivers()
```

## Principle 7: No HTTP Concerns

Services should never know about HTTP requests, responses, or status codes.

```python
# ✅ Good: Service has no HTTP knowledge
class DeviceService:
    @staticmethod
    def get_device(*, device_id: int) -> Receiver:
        return Receiver.objects.get(id=device_id)

# In view:
try:
    device = DeviceService.get_device(device_id=device_id)
    return Response({'device': ReceiverSerializer(device).data})
except Receiver.DoesNotExist:
    return Response({'error': 'Not found'}, status=404)
```

```python
# ❌ Bad: Service knows about HTTP
class DeviceService:
    @staticmethod
    def get_device(*, device_id: int) -> Response:
        try:
            device = Receiver.objects.get(id=device_id)
            return Response({'device': device.id})
        except Receiver.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)
```

## Principle 8: Use TYPE_CHECKING for Type Hints

Import model types inside `TYPE_CHECKING` blocks to avoid circular imports.

```python
# ✅ Good: TYPE_CHECKING prevents circular imports
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

if TYPE_CHECKING:
    from micboard.models import Receiver, Transmitter

@staticmethod
def get_devices() -> QuerySet:
    return Receiver.objects.filter(active=True)
```

```python
# ❌ Bad: Direct import causes circular imports
from micboard.models import Receiver, Transmitter

@staticmethod
def get_devices() -> list[Receiver]:
    # May cause circular import errors in complex projects
    return list(Receiver.objects.filter(active=True))
```

## Principle 9: Method Naming Conventions

Follow consistent naming for common operations:

```python
# ✅ Good: Consistent naming
class DeviceService:
    @staticmethod
    def create_*(...) -> Model:           # Create operations
        pass

    @staticmethod
    def update_*(...) -> Model:           # Update operations
        pass

    @staticmethod
    def delete_*(...) -> None:            # Delete operations
        pass

    @staticmethod
    def get_*(...) -> Model | QuerySet:   # Retrieve operations
        pass

    @staticmethod
    def sync_*(...) -> None | dict:       # Synchronization operations
        pass
```

## Principle 10: Docstrings for All Methods

Use docstrings with Args, Returns, Raises sections.

```python
# ✅ Good: Complete docstring
@staticmethod
def create_assignment(
    *,
    user: User,
    device: Receiver | Transmitter,
    *,
    alert_enabled: bool = True
) -> Assignment:
    """Create a new user-device assignment.

    Args:
        user: User instance.
        device: Device to assign (Receiver or Transmitter).
        alert_enabled: Enable alerts for this assignment. Defaults to True.

    Returns:
        Created Assignment instance.

    Raises:
        ValueError: If assignment already exists for this user and device.
    """
    pass
```

## Principle 11: DRY - Extract Common Queries

Avoid repeating the same query logic across methods.

```python
# ✅ Good: Extract common query
class DeviceService:
    @staticmethod
    def _get_active_base_queryset() -> QuerySet:
        """Base queryset for active devices."""
        return Receiver.objects.filter(active=True)

    @staticmethod
    def get_active_receivers() -> QuerySet:
        """Get all active receivers."""
        return DeviceService._get_active_base_queryset()

    @staticmethod
    def get_online_receivers() -> QuerySet:
        """Get active, online receivers."""
        return DeviceService._get_active_base_queryset().filter(online=True)
```

## Principle 12: Use Utility Functions

Leverage utility functions for pagination, filtering, and transformation.

```python
# ✅ Good: Use utilities
from micboard.services import paginate_queryset, filter_by_search

class DeviceService:
    @staticmethod
    def search_devices(
        *,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20
    ):
        """Search devices with pagination."""
        devices = Receiver.objects.filter(active=True)
        devices = filter_by_search(
            queryset=devices,
            search_fields=['name', 'model', 'ip_address'],
            query=query
        )
        return paginate_queryset(
            queryset=devices,
            page=page,
            page_size=page_size
        )
```

## Principle 13: Atomic Operations

Use database transactions for operations that affect multiple models.

```python
# ✅ Good: Use transaction
from django.db import transaction

@staticmethod
def transfer_device_location(
    *,
    device: Receiver,
    *,
    new_location: Location
) -> Receiver:
    """Move device to new location atomically."""
    with transaction.atomic():
        old_location = device.location
        device.location = new_location
        device.save()

        # Additional operations that should all succeed together
        ActivityLog.objects.create(
            action='device_moved',
            device=device,
            old_value=old_location.id,
            new_value=new_location.id
        )

    return device
```

## Principle 14: Logging

Add logging for important operations and errors.

```python
# ✅ Good: Add logging
import logging

logger = logging.getLogger(__name__)

class DeviceService:
    @staticmethod
    def sync_device_status(
        *,
        device_obj: Receiver,
        *,
        online: bool
    ) -> None:
        """Update device online status."""
        if device_obj.online != online:
            old_status = device_obj.online
            device_obj.online = online
            device_obj.save()

            logger.info(
                f"Device {device_obj.id} status changed: {old_status} -> {online}"
            )
```

## Testing Services

```python
# ✅ Good: Test services independently
from django.test import TestCase
from micboard.services import DeviceService
from micboard.models import Receiver

class DeviceServiceTestCase(TestCase):
    def setUp(self):
        self.receiver = Receiver.objects.create(
            ip_address="192.168.1.1",
            active=True,
            online=False
        )

    def test_sync_device_status_online(self):
        """Test setting device online."""
        DeviceService.sync_device_status(device_obj=self.receiver, online=True)
        self.receiver.refresh_from_db()
        self.assertTrue(self.receiver.online)

    def test_get_active_receivers(self):
        """Test fetching active receivers."""
        inactive = Receiver.objects.create(
            ip_address="192.168.1.2",
            active=False
        )
        active = DeviceService.get_active_receivers()

        self.assertEqual(active.count(), 1)
        self.assertIn(self.receiver, active)
        self.assertNotIn(inactive, active)
```

## Summary Checklist

- [ ] All parameters are keyword-only (use `*` separator)
- [ ] All methods have type hints
- [ ] All methods have docstrings
- [ ] Methods return domain objects, not serialized data
- [ ] Exceptions are explicit and domain-specific
- [ ] Service methods are static
- [ ] No HTTP concerns in services
- [ ] No instance state in service classes
- [ ] Common queries extracted to helper methods
- [ ] Use utility functions for pagination, filtering, etc.
- [ ] Logging for important operations
- [ ] Tests for service methods
