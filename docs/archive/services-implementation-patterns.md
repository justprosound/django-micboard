
# Service Layer Implementation Patterns

This guide shows how to integrate services into common django-micboard patterns.

## Pattern 1: Polling Management Command

### Current Implementation

```python
# micboard/management/commands/poll_devices.py
from django.core.management.base import BaseCommand
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Receiver, Transmitter

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Get plugin
        plugin = get_manufacturer_plugin('shure')

        # Get devices from API
        devices = plugin.get_devices()

        # Update models directly
        for device_data in devices:
            receiver = Receiver.objects.get(device_id=device_data['id'])
            receiver.online = device_data['online']
            receiver.battery_level = device_data.get('battery')
            receiver.firmware = device_data.get('firmware')
            receiver.save()
```

### Using Services

```python
# micboard/management/commands/poll_devices.py
from django.core.management.base import BaseCommand
from micboard.services import (
    ManufacturerService,
    DeviceService,
    ConnectionHealthService
)

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Get active manufacturers
        manufacturers = ManufacturerService.get_active_manufacturers()

        for mfg_config in manufacturers:
            self.stdout.write(f"Syncing {mfg_config.manufacturer_code}...")

            # Sync all devices from manufacturer
            result = ManufacturerService.sync_devices_for_manufacturer(
                manufacturer_code=mfg_config.manufacturer_code
            )

            if result['success']:
                self.stdout.write(
                    f"✓ Added: {result['devices_added']}, "
                    f"Updated: {result['devices_updated']}"
                )
            else:
                for error in result['errors']:
                    self.stdout.write(self.style.ERROR(f"✗ {error}"))

        # Monitor connection health
        unhealthy = ConnectionHealthService.get_unhealthy_connections()
        for conn in unhealthy:
            self.stdout.write(f"⚠ Unhealthy connection: {conn.id}")
            ConnectionHealthService.update_connection_status(
                connection=conn,
                status='error'
            )
```

## Pattern 2: REST API View

### Current Implementation

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Receiver
from micboard.serializers import ReceiverSerializer

class ReceiverListView(APIView):
    def get(self, request):
        # Direct model query
        receivers = Receiver.objects.filter(active=True)
        serializer = ReceiverSerializer(receivers, many=True)
        return Response(serializer.data)

    def post(self, request):
        # Direct model creation
        receiver = Receiver.objects.create(
            ip_address=request.data['ip_address'],
            name=request.data['name'],
            active=True
        )
        serializer = ReceiverSerializer(receiver)
        return Response(serializer.data, status=201)
```

### Using Services

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from micboard.services import DeviceService
from micboard.serializers import ReceiverSerializer
from micboard.decorators import rate_limit_view

class ReceiverListView(APIView):
    @rate_limit_view(max_requests=100, window_seconds=60)
    def get(self, request):
        # Use service
        receivers = DeviceService.get_active_receivers()

        # Handle search
        if search := request.query_params.get('search'):
            receivers = DeviceService.search_devices(query=search)

        # Serialize
        serializer = ReceiverSerializer(receivers, many=True)
        return Response(serializer.data)

    @rate_limit_view(max_requests=20, window_seconds=60)
    def post(self, request):
        try:
            # Use service for creation
            receiver = Receiver.objects.create(
                ip_address=request.data['ip_address'],
                name=request.data['name'],
                active=True
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        serializer = ReceiverSerializer(receiver)
        return Response(serializer.data, status=201)
```

## Pattern 3: User Assignment Workflow

### Current Implementation

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Assignment, Receiver

class AssignmentView(APIView):
    def post(self, request):
        user = request.user
        receiver = Receiver.objects.get(id=request.data['device_id'])

        # Check if already assigned
        if Assignment.objects.filter(user=user, device_id=receiver.id).exists():
            return Response({'error': 'Already assigned'}, status=400)

        # Create assignment
        assignment = Assignment.objects.create(
            user=user,
            device_id=receiver.id,
            alert_enabled=request.data.get('alert_enabled', True)
        )

        # Serialize
        return Response({'id': assignment.id, 'user': user.id}, status=201)
```

### Using Services

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.services import AssignmentService, AssignmentAlreadyExistsError
from micboard.models import Receiver
from micboard.serializers import AssignmentSerializer
from micboard.decorators import rate_limit_view

class AssignmentView(APIView):
    @rate_limit_view(max_requests=50, window_seconds=60)
    def post(self, request):
        user = request.user
        device = Receiver.objects.get(id=request.data['device_id'])

        try:
            # Use service with validation
            assignment = AssignmentService.create_assignment(
                user=user,
                device=device,
                alert_enabled=request.data.get('alert_enabled', True),
                notes=request.data.get('notes', '')
            )
        except AssignmentAlreadyExistsError as e:
            return Response({'error': str(e)}, status=400)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        serializer = AssignmentSerializer(assignment)
        return Response(serializer.data, status=201)

    def put(self, request, assignment_id):
        try:
            assignment = Assignment.objects.get(id=assignment_id, user=request.user)
        except Assignment.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        # Use service to update
        updated = AssignmentService.update_assignment(
            assignment=assignment,
            alert_enabled=request.data.get('alert_enabled'),
            notes=request.data.get('notes')
        )

        serializer = AssignmentSerializer(updated)
        return Response(serializer.data)
```

## Pattern 4: Connection Health Monitoring

### Current Implementation

```python
# myapp/management/commands/monitor_connections.py
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from micboard.models import RealTimeConnection

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Check all active connections
        for conn in RealTimeConnection.objects.filter(status='connected'):
            timeout = now() - timedelta(seconds=60)

            # Check if heartbeat is stale
            if not conn.last_heartbeat or conn.last_heartbeat < timeout:
                conn.status = 'error'
                conn.error_count = (conn.error_count or 0) + 1
                conn.save()

                self.stdout.write(f"Connection {conn.id} marked as error")
```

### Using Services

```python
# myapp/management/commands/monitor_connections.py
from django.core.management.base import BaseCommand
from micboard.services import ConnectionHealthService

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Get unhealthy connections
        unhealthy = ConnectionHealthService.get_unhealthy_connections(
            heartbeat_timeout_seconds=60
        )

        for conn in unhealthy:
            # Update status using service
            ConnectionHealthService.update_connection_status(
                connection=conn,
                status='error'
            )
            self.stdout.write(f"Connection {conn.id} marked as error")

        # Get stats
        stats = ConnectionHealthService.get_connection_stats()
        self.stdout.write(
            f"Active: {stats['active_connections']}, "
            f"Errors: {stats['error_connections']}"
        )
```

## Pattern 5: Pagination in Views

### Current Implementation

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Receiver

class ReceiverListPaginatedView(APIView):
    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Manual pagination
        queryset = Receiver.objects.filter(active=True)
        total = queryset.count()
        offset = (page - 1) * page_size

        receivers = queryset[offset:offset + page_size]

        return Response({
            'items': [{'id': r.id, 'name': r.name} for r in receivers],
            'total': total,
            'page': page,
            'page_size': page_size
        })
```

### Using Services

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.services import DeviceService, paginate_queryset
from micboard.serializers import ReceiverSerializer

class ReceiverListPaginatedView(APIView):
    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Get all active
        queryset = DeviceService.get_active_receivers()

        # Paginate using utility
        result = paginate_queryset(
            queryset=queryset,
            page=page,
            page_size=page_size
        )

        serializer = ReceiverSerializer(result.items, many=True)

        return Response({
            'items': serializer.data,
            'pagination': {
                'total': result.total_count,
                'page': result.page,
                'page_size': result.page_size,
                'total_pages': result.total_pages,
                'has_next': result.has_next,
                'has_previous': result.has_previous
            }
        })
```

## Pattern 6: Search Implementation

### Current Implementation

```python
# myapp/views.py
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Receiver

class SearchView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '')

        if not query:
            return Response({'results': []})

        # Manual search
        q_objects = Q(name__icontains=query) | Q(ip_address__icontains=query) | Q(model__icontains=query)
        receivers = Receiver.objects.filter(q_objects, active=True)

        return Response({
            'results': [
                {'id': r.id, 'name': r.name, 'ip': r.ip_address}
                for r in receivers
            ]
        })
```

### Using Services

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.services import DeviceService, filter_by_search
from micboard.models import Receiver
from micboard.serializers import ReceiverSerializer

class SearchView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '')

        if not query:
            return Response({'results': []})

        # Use service
        queryset = Receiver.objects.filter(active=True)
        results = filter_by_search(
            queryset=queryset,
            search_fields=['name', 'ip_address', 'model'],
            query=query
        )

        serializer = ReceiverSerializer(results, many=True)
        return Response({'results': serializer.data})
```

## Pattern 7: Location Management

### Current Implementation

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Location, Receiver

class LocationView(APIView):
    def post(self, request):
        name = request.data['name']

        # Check if exists
        if Location.objects.filter(name=name).exists():
            return Response({'error': 'Duplicate'}, status=400)

        # Create
        location = Location.objects.create(
            name=name,
            description=request.data.get('description', '')
        )

        return Response({'id': location.id, 'name': location.name})

    def get(self, request, location_id):
        location = Location.objects.get(id=location_id)

        # Get devices
        receivers = Receiver.objects.filter(location=location, active=True)

        return Response({
            'id': location.id,
            'name': location.name,
            'devices': [{'id': r.id, 'name': r.name} for r in receivers]
        })
```

### Using Services

```python
# myapp/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.services import (
    LocationService,
    DeviceService,
    LocationAlreadyExistsError
)
from micboard.serializers import LocationSerializer, ReceiverSerializer

class LocationView(APIView):
    def post(self, request):
        try:
            location = LocationService.create_location(
                name=request.data['name'],
                description=request.data.get('description', '')
            )
        except LocationAlreadyExistsError as e:
            return Response({'error': str(e)}, status=400)

        serializer = LocationSerializer(location)
        return Response(serializer.data, status=201)

    def get(self, request, location_id):
        location = Location.objects.get(id=location_id)

        # Use service for devices
        devices = LocationService.get_devices_in_location(location=location)

        serializer = LocationSerializer(location)
        devices_serializer = ReceiverSerializer(devices, many=True)

        return Response({
            **serializer.data,
            'devices': devices_serializer.data
        })
```

## Pattern 8: Django Signal Handler

### Current Implementation

```python
# myapp/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from micboard.models import Receiver, ActivityLog

@receiver(post_save, sender=Receiver)
def on_receiver_created(sender, instance, created, **kwargs):
    if created:
        # Log activity
        ActivityLog.objects.create(
            action='device_created',
            device_id=instance.id,
            user_id=None
        )

        # Send notification
        notify_admin(f"New receiver: {instance.name}")
```

### Using Services

```python
# myapp/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from micboard.models import Receiver, ActivityLog
from micboard.services import ConnectionHealthService

@receiver(post_save, sender=Receiver)
def on_receiver_created(sender, instance, created, **kwargs):
    if created:
        # Keep signal lightweight - only for side effects/notifications
        ActivityLog.objects.create(
            action='device_created',
            device_id=instance.id,
            user_id=None
        )

        # Use service to get stats
        stats = ConnectionHealthService.get_connection_stats()

        # Conditional notification
        if stats['active_connections'] == 0:
            notify_admin(f"⚠ No active connections but receiver added: {instance.name}")
```

## Summary

When refactoring to use services:

1. **Identify** repeated model operations in views/commands
2. **Create** service method for the operation
3. **Replace** direct model access with service call
4. **Handle** exceptions raised by service
5. **Test** the service method independently
6. **Document** the new pattern in code comments

This approach ensures:
- ✅ DRY principle - no repeated code
- ✅ Testability - services can be tested independently
- ✅ Maintainability - business logic is centralized
- ✅ Clarity - explicit service interface documents capabilities
- ✅ Reusability - services work in views, commands, signals, tasks
