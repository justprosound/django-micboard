# Services Layer Quick Reference

Quick lookup for common service operations.

## Imports

```python
from micboard.services import (
    DeviceService,
    AssignmentService,
    ManufacturerService,
    ConnectionHealthService,
    LocationService,
    DiscoveryService,
    # Utilities
    paginate_queryset,
    filter_by_search,
    # Exceptions
    AssignmentAlreadyExistsError,
    DeviceNotFoundError,
)
```

## Device Management

```python
# Get devices
DeviceService.get_active_receivers()           # QuerySet
DeviceService.get_active_transmitters()        # QuerySet
DeviceService.get_device_by_ip(ip_address="192.168.1.1")  # Device or None

# Update device
DeviceService.sync_device_status(device_obj=device, online=True)
DeviceService.sync_device_battery(device_obj=device, battery_level=75)

# Search
DeviceService.search_devices(query="micboard")  # QuerySet
DeviceService.count_online_devices()           # {'receivers': 5, 'transmitters': 3}

# Location-specific
DeviceService.get_receivers_by_location(location_id=1)
DeviceService.get_transmitters_by_charger(charger=charger)
```

## Assignments

```python
# Create
AssignmentService.create_assignment(
    user=user,
    device=receiver,
    alert_enabled=True,
    notes="Main stage"
)

# Read
AssignmentService.get_user_assignments(user=user)
AssignmentService.get_device_assignments(device_id=1)
AssignmentService.get_users_with_alerts(device_id=1)
AssignmentService.has_assignment(user_id=1, device_id=1)

# Update
AssignmentService.update_assignment(
    assignment=assignment,
    alert_enabled=False,
    notes="Updated"
)

# Delete
AssignmentService.delete_assignment(assignment=assignment)
```

## Manufacturer & Sync

```python
# Sync
ManufacturerService.sync_devices_for_manufacturer(manufacturer_code='shure')
# Returns: {
#     'success': bool,
#     'devices_added': int,
#     'devices_updated': int,
#     'devices_removed': int,
#     'errors': [str]
# }

# Test
ManufacturerService.test_manufacturer_connection(manufacturer_code='shure')
# Returns: {
#     'success': bool,
#     'message': str,
#     'response_time_ms': float | None
# }

# Query
ManufacturerService.get_active_manufacturers()
ManufacturerService.get_manufacturer_config(manufacturer_code='shure')
ManufacturerService.get_plugin(manufacturer_code='shure')
ManufacturerService.get_device_status(manufacturer_code='shure', device_id='id')
```

## Connection Health

```python
# Create
ConnectionHealthService.create_connection(
    manufacturer_code='shure',
    connection_type='websocket',
    status='connecting'
)

# Update
ConnectionHealthService.update_connection_status(connection=conn, status='connected')

# Record events
ConnectionHealthService.record_heartbeat(connection=conn)
ConnectionHealthService.record_error(connection=conn, error_message="Timeout")

# Check status
ConnectionHealthService.is_healthy(connection=conn, heartbeat_timeout_seconds=60)

# Query
ConnectionHealthService.get_active_connections()
ConnectionHealthService.get_unhealthy_connections(heartbeat_timeout_seconds=60)
ConnectionHealthService.get_connections_by_manufacturer(manufacturer_code='shure')

# Analytics
ConnectionHealthService.get_connection_stats()
ConnectionHealthService.get_connection_uptime(connection=conn)
ConnectionHealthService.cleanup_stale_connections(max_age_hours=24)
```

## Locations

```python
# Create
LocationService.create_location(name="Main Stage", description="Main area")

# Read
LocationService.get_all_locations()
LocationService.get_location_by_name(name="Main Stage")
LocationService.get_location_device_counts()
LocationService.get_devices_in_location(location=location)

# Update
LocationService.update_location(location=location, name="Left Stage")

# Assign device
LocationService.assign_device_to_location(device=receiver, location=location)
LocationService.unassign_device_from_location(device=receiver)

# Delete
LocationService.delete_location(location=location)
```

## Discovery

```python
# Create task
DiscoveryService.create_discovery_task(
    name="Main Network",
    discovery_type='cidr',
    target='192.168.1.0/24',
    enabled=True
)

# Manage
DiscoveryService.get_enabled_discovery_tasks()
DiscoveryService.update_discovery_task(task=task, enabled=False)
DiscoveryService.execute_discovery(task=task)
DiscoveryService.delete_discovery_task(task=task)

# Register
DiscoveryService.register_discovered_device(
    ip_address='192.168.1.50',
    device_type='receiver',
    name='New Receiver',
    manufacturer_code='shure'
)

# Results
DiscoveryService.get_discovery_results(task=task)
DiscoveryService.get_undiscovered_devices()
```

## Utilities

```python
from micboard.services import paginate_queryset, filter_by_search

# Pagination
result = paginate_queryset(
    queryset=queryset,
    page=1,
    page_size=20
)
# result.items, result.total_count, result.total_pages, result.has_next, result.has_previous

# Search
results = filter_by_search(
    queryset=Device.objects.all(),
    search_fields=['name', 'ip_address', 'model'],
    query='micboard'
)
```

## Exception Handling

```python
try:
    assignment = AssignmentService.create_assignment(user=user, device=device)
except AssignmentAlreadyExistsError as e:
    # Handle: user already assigned to this device
    pass

try:
    location = LocationService.create_location(name="Stage")
except LocationAlreadyExistsError as e:
    # Handle: location name already exists
    pass

try:
    device = Receiver.objects.get(id=device_id)
except Receiver.DoesNotExist:
    # Handle in view layer, not service
    pass
```

## Common Patterns

### View - Get and Serialize

```python
def device_list(request):
    devices = DeviceService.get_active_receivers()
    serializer = ReceiverSerializer(devices, many=True)
    return Response(serializer.data)
```

### View - Create with Validation

```python
def create_assignment(request):
    try:
        assignment = AssignmentService.create_assignment(
            user=request.user,
            device=Receiver.objects.get(id=request.data['device_id']),
            alert_enabled=request.data.get('alert_enabled', True)
        )
    except AssignmentAlreadyExistsError as e:
        return Response({'error': str(e)}, status=400)

    serializer = AssignmentSerializer(assignment)
    return Response(serializer.data, status=201)
```

### Management Command - Sync

```python
def handle(self, *args, **options):
    manufacturers = ManufacturerService.get_active_manufacturers()

    for mfg_config in manufacturers:
        result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=mfg_config.manufacturer_code
        )
        self.stdout.write(f"Synced: {result}")
```

### Management Command - Health Check

```python
def handle(self, *args, **options):
    unhealthy = ConnectionHealthService.get_unhealthy_connections()

    for conn in unhealthy:
        ConnectionHealthService.update_connection_status(
            connection=conn,
            status='error'
        )
```

### Django Signal - Lightweight

```python
@receiver(post_save, sender=Receiver)
def on_receiver_created(sender, instance, created, **kwargs):
    if created:
        # Only side effects, not business logic
        ActivityLog.objects.create(action='device_created', device=instance)
```

### Pagination in View

```python
def device_list(request):
    page = int(request.query_params.get('page', 1))

    result = paginate_queryset(
        queryset=DeviceService.get_active_receivers(),
        page=page,
        page_size=20
    )

    serializer = ReceiverSerializer(result.items, many=True)
    return Response({
        'items': serializer.data,
        'pagination': {
            'total': result.total_count,
            'page': result.page,
            'has_next': result.has_next,
            'has_previous': result.has_previous
        }
    })
```

### Search in View

```python
def search(request):
    query = request.query_params.get('q', '')

    results = filter_by_search(
        queryset=Receiver.objects.filter(active=True),
        search_fields=['name', 'ip_address', 'model'],
        query=query
    )

    serializer = ReceiverSerializer(results, many=True)
    return Response({'results': serializer.data})
```

## Error Handling Strategy

```python
# ✅ Good: Handle expected exceptions
try:
    assignment = AssignmentService.create_assignment(...)
except AssignmentAlreadyExistsError:
    return Response({'error': 'Already assigned'}, status=400)
except ValueError as e:
    return Response({'error': str(e)}, status=400)

# ✅ Good: Let model exceptions bubble up and handle in view
try:
    device = Receiver.objects.get(id=device_id)
except Receiver.DoesNotExist:
    return Response({'error': 'Device not found'}, status=404)

# ❌ Bad: Too broad exception handling
try:
    result = service.operation()
except Exception:
    return Response({'error': 'Error'}, status=500)
```

## Checklist for New Service Methods

When adding a new service method:

- [ ] Use keyword-only parameters (use `*`)
- [ ] Add type hints for all parameters and return value
- [ ] Add docstring with Args, Returns, Raises sections
- [ ] Consider what exceptions to raise
- [ ] Return domain objects, not dicts
- [ ] Keep logic database-agnostic where possible
- [ ] Test the method independently
- [ ] Add example usage in docstring or docs

## Documentation Links

- **Full API**: [Services Layer Documentation](services-layer.md)
- **Best Practices**: [Best Practices Guide](services-best-practices.md)
- **Implementation**: [Implementation Patterns](services-implementation-patterns.md)
- **Refactoring**: [Refactoring Guide](refactoring-guide.md)
- **Summary**: [Phase 1 Summary](phase1-summary.md)
