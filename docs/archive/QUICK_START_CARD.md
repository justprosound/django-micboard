
# Django Micboard - Service Layer Quick Start Card

## 🚀 5-Minute Quick Start

### 1. Import Services
```python
from micboard.services import (
    DeviceService,
    AssignmentService,
    ManufacturerService,
    ConnectionHealthService,
    LocationService,
    DiscoveryService,
)
```

### 2. Use Services (Most Common Operations)
```python
# Get active devices
receivers = DeviceService.get_active_receivers()
transmitters = DeviceService.get_active_transmitters()

# Update device status
DeviceService.sync_device_status(device_obj=receiver, online=True)

# Create assignment
assignment = AssignmentService.create_assignment(
    user=request.user,
    device=receiver,
    alert_enabled=True
)

# Sync manufacturer devices
result = ManufacturerService.sync_devices_for_manufacturer(
    manufacturer_code='shure'
)
```

### 3. Handle Exceptions
```python
from micboard.services import (
    AssignmentAlreadyExistsError,
    DeviceNotFoundError,
    ManufacturerNotFoundError,
)

try:
    assignment = AssignmentService.create_assignment(...)
except AssignmentAlreadyExistsError:
    # Handle duplicate
    pass
except ValueError as e:
    # Handle invalid data
    pass
```

---

## 📖 Documentation Links

| Need | Link |
|------|------|
| **Master Guide** | `docs/00_START_HERE.md` |
| **Quick Reference** | `docs/services-quick-reference.md` |
| **Best Practices** | `docs/services-best-practices.md` |
| **Integration** | `docs/PHASE2_INTEGRATION_GUIDE.md` |
| **Examples** | `docs/services-implementation-patterns.md` |

---

## ⚡ Common Patterns

### Device Queries
```python
# Active only
receivers = DeviceService.get_active_receivers()

# Online only
online = DeviceService.get_online_receivers()

# Search
results = DeviceService.search_devices(query="stage")

# Count
stats = DeviceService.count_online_devices()
# Returns: {'receivers': 5, 'transmitters': 10}
```

### Assignments
```python
# Get user's assignments
assignments = AssignmentService.get_user_assignments(user=user)

# Get device assignment
assignment = AssignmentService.get_device_assignment(device=receiver)

# Update alerts
AssignmentService.update_assignment(
    assignment=assignment,
    alert_enabled=False
)

# Delete
AssignmentService.delete_assignment(assignment=assignment)
```

### Manufacturer Sync
```python
# Sync all devices
result = ManufacturerService.sync_devices_for_manufacturer(
    manufacturer_code='shure'
)
# Returns: {
#     'success': True,
#     'devices_added': 5,
#     'devices_updated': 3,
#     'devices_removed': 0,
#     'errors': []
# }

# Test connection
is_healthy = ManufacturerService.test_manufacturer_connection(
    manufacturer_code='shure'
)
```

### Connection Health
```python
# Get unhealthy connections
unhealthy = ConnectionHealthService.get_unhealthy_connections(
    heartbeat_timeout_seconds=60
)

# Update status
ConnectionHealthService.update_connection_status(
    connection=conn,
    status='error'
)

# Get stats
stats = ConnectionHealthService.get_connection_stats()
# Returns: {
#     'active_connections': 5,
#     'error_connections': 1,
#     'total_connections': 6
# }
```

### Locations
```python
# Create
location = LocationService.create_location(
    name="Main Stage",
    description="Main performance area"
)

# Get with device counts
locations = LocationService.get_location_device_counts()

# Assign device
LocationService.assign_device_to_location(
    device=receiver,
    location=location
)
```

### Pagination
```python
from micboard.services import paginate_queryset

# Paginate results
result = paginate_queryset(
    queryset=receivers,
    page=1,
    page_size=20
)
# Returns: PaginatedResult(
#     items=[...],
#     total_count=45,
#     page=1,
#     page_size=20,
#     total_pages=3
# )
```

---

## 🧪 Testing

### Import Test Utilities
```python
from micboard.test_utils import (
    ServiceTestCase,
    create_test_user,
    create_test_receiver,
    create_test_transmitter,
    create_test_location,
    create_test_assignment,
)
```

### Write Tests
```python
class TestDeviceService(ServiceTestCase):
    def test_sync_device_status(self):
        # Fixtures already available from ServiceTestCase
        receiver = self.receiver1  # Pre-created

        DeviceService.sync_device_status(
            device_obj=receiver,
            online=False
        )

        receiver.refresh_from_db()
        self.assertFalse(receiver.online)

    def test_custom_fixture(self):
        # Or create custom fixtures
        receiver = create_test_receiver(
            name="Custom Receiver",
            online=True
        )
        self.assertTrue(receiver.online)
```

---

## ✅ Best Practices Checklist

- [ ] Always use keyword-only parameters (after `*`)
- [ ] Always catch specific exceptions
- [ ] Never put business logic in views
- [ ] Never put business logic in signals
- [ ] Always use services for data operations
- [ ] Always add type hints
- [ ] Always add docstrings
- [ ] Test with `ServiceTestCase` base class
- [ ] Use helper functions for fixtures
- [ ] Check docs when unsure

---

## 🎯 Service Methods Count

| Service | Methods | Purpose |
|---------|---------|---------|
| DeviceService | 11 | Device management |
| AssignmentService | 8 | User assignments |
| ManufacturerService | 7 | API sync |
| ConnectionHealthService | 11 | Health monitoring |
| LocationService | 9 | Location management |
| DiscoveryService | 9 | Device discovery |

**Total: 69 production-ready methods**

---

## 🔥 Most Used Methods (Top 10)

1. `DeviceService.get_active_receivers()`
2. `DeviceService.sync_device_status()`
3. `AssignmentService.create_assignment()`
4. `AssignmentService.get_user_assignments()`
5. `ManufacturerService.sync_devices_for_manufacturer()`
6. `ConnectionHealthService.get_unhealthy_connections()`
7. `DeviceService.search_devices()`
8. `LocationService.create_location()`
9. `AssignmentService.update_assignment()`
10. `DeviceService.count_online_devices()`

---

## 📞 Help & Support

**Got a question?** Check in this order:

1. This quick start card
2. `docs/services-quick-reference.md` (method lookup)
3. `docs/services-best-practices.md` (patterns)
4. `docs/services-implementation-patterns.md` (examples)
5. `docs/PHASE2_INTEGRATION_GUIDE.md` (integration help)
6. Ask your team lead

---

## 🐛 Debugging Tips

### Service not working?
1. Check if you're using keyword arguments
2. Check if exception is being raised
3. Check the docstring for expected parameters
4. Look for similar code in templates

### Import error?
```python
# Correct
from micboard.services import DeviceService

# Also correct
from micboard.services import (
    DeviceService,
    AssignmentService,
)
```

### Type error?
- Check parameter types in docstring
- Use type hints in your code
- IDE should show expected types

---

## 🎓 Learning Path

### Day 1 (30 min)
- Read this card
- Try 3-5 common operations
- Review quick reference

### Week 1 (2 hours)
- Read `services-layer.md`
- Review your area's template
- Write first integration

### Week 2 (2 hours)
- Study best practices guide
- Review implementation patterns
- Refactor your first component

---

## 💡 Pro Tips

1. **Always use keyword arguments** for optional params
2. **Check the return type** in docstrings
3. **Catch specific exceptions** not `Exception`
4. **Use test utilities** for faster test writing
5. **Reference templates** when refactoring
6. **Keep signals minimal** - logic in services
7. **Type hints help** - your IDE will thank you
8. **Read docstrings** - they have all the info

---

**Print this card and keep it handy! 📌**

**Version:** Phase 1 Complete + Phase 2 Ready
**Updated:** November 2025
