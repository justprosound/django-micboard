# Phase 2: Integration Checklist

**Status:** Ready to Begin
**Prerequisites:** ✅ Phase 1 Complete (Lifecycle Infrastructure)

## Overview

Integrate the new `DeviceLifecycleManager` with existing Shure polling infrastructure and manufacturer integrations.

## Integration Tasks

### 1. Shure Integration Refactoring

**Files to Update:**
- [ ] `micboard/integrations/shure/client.py` - Review API methods
- [ ] `micboard/manufacturers/shure/plugin.py` - Convert to service pattern
- [ ] `micboard/management/commands/poll_devices.py` - Use lifecycle manager

**Tasks:**

#### 1.1 Review Current Shure Client
```bash
# Examine current implementation
cat micboard/integrations/shure/client.py | grep "def "
```

**Action Items:**
- [ ] Document all API methods available
- [ ] Identify which methods map to lifecycle operations
- [ ] Check if `update_device()` method exists (for push sync)
- [ ] Verify `list_devices()` returns expected format

#### 1.2 Convert Shure Plugin to Service

**Before Pattern:**
```python
# micboard/manufacturers/shure/plugin.py
class ShurePlugin(ManufacturerPlugin):
    def get_devices(self):
        # Returns device data
```

**After Pattern:**
```python
# Use micboard/services/shure_service_example.py as template
class ShureService(ManufacturerService):
    def poll_devices(self):
        # Use lifecycle manager
        for api_device in self.get_client().list_devices():
            self.update_device_from_api(receiver, api_device)
            self.check_device_health(receiver)
```

**Action Items:**
- [ ] Create `micboard/services/shure_service.py` (copy from example)
- [ ] Register service in `micboard/services/__init__.py`
- [ ] Update `poll_devices` command to use service
- [ ] Test with existing Shure System API

#### 1.3 Update Polling Command

**File:** `micboard/management/commands/poll_devices.py`

**Changes Needed:**
```python
# OLD
from micboard.manufacturers import get_manufacturer_plugin
plugin = get_manufacturer_plugin('shure')
devices = plugin.get_devices()

# NEW
from micboard.services.manufacturer_service import get_service
service = get_service('shure')
devices = service.poll_devices()  # Uses lifecycle manager internally
```

**Action Items:**
- [ ] Refactor command to use `get_service()` instead of plugin
- [ ] Remove manual model updates (handled by lifecycle manager)
- [ ] Remove signal emissions (handled by service)
- [ ] Add error handling and logging
- [ ] Test polling cycle end-to-end

### 2. WebSocket Integration Testing

**Files to Check:**
- [ ] `micboard/websockets/consumers.py` - WebSocket consumer
- [ ] `demo/routing.py` - ASGI routing configuration

**Tasks:**

#### 2.1 Verify Signal Handlers
```python
# Should already be wired up via micboard/signals/handlers.py
@receiver(device_status_changed)
def broadcast_device_status(...):
    # Broadcasts to 'micboard_updates' group
```

**Action Items:**
- [ ] Verify handlers are registered (check `micboard/apps.py`)
- [ ] Check WebSocket consumer handles `device_status_update` type
- [ ] Test signal emission reaches consumer
- [ ] Verify UI receives status updates

#### 2.2 Test Real-Time Updates
```bash
# Terminal 1: Start server
python manage.py runserver

# Terminal 2: WebSocket client
python -c "
import asyncio
import websockets

async def test():
    uri = 'ws://localhost:8000/ws/micboard/'
    async with websockets.connect(uri) as ws:
        while True:
            msg = await ws.recv()
            print(f'Received: {msg}')

asyncio.run(test())
"
```

**Action Items:**
- [ ] Connect WebSocket client
- [ ] Trigger device status change (mark online/offline)
- [ ] Verify message received on WebSocket
- [ ] Check message format matches expectations

### 3. Admin Interface Integration

**Files to Update:**
- [ ] `micboard/admin/receivers.py` - Add admin actions
- [ ] `micboard/admin/transmitters.py` - Add admin actions

**Tasks:**

#### 3.1 Add Lifecycle Admin Actions

**Example Implementation:**
```python
from micboard.services.device_lifecycle import get_lifecycle_manager

@admin.action(description='Mark selected devices as online')
def mark_online_action(modeladmin, request, queryset):
    lifecycle = get_lifecycle_manager('shure')
    count = 0
    for device in queryset:
        if lifecycle.mark_online(device):
            count += 1
    modeladmin.message_user(request, f'{count} devices marked online')

@admin.action(description='Put in maintenance mode')
def maintenance_mode_action(modeladmin, request, queryset):
    lifecycle = get_lifecycle_manager('shure')
    count = 0
    for device in queryset:
        if lifecycle.mark_maintenance(device, reason=f'Admin action by {request.user.username}'):
            count += 1
    modeladmin.message_user(request, f'{count} devices in maintenance mode')

class ReceiverAdmin(admin.ModelAdmin):
    actions = [mark_online_action, maintenance_mode_action]
```

**Action Items:**
- [ ] Add admin actions for common transitions
  - [ ] Mark Online
  - [ ] Mark Offline
  - [ ] Mark Degraded
  - [ ] Maintenance Mode
  - [ ] Retire Device
- [ ] Add admin action for force sync to API
- [ ] Test actions in Django admin
- [ ] Verify ActivityLog entries created

#### 3.2 Update Admin List Display

**Show Status Field:**
```python
class ReceiverAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip', 'status', 'is_active', 'last_seen', 'manufacturer']
    list_filter = ['status', 'is_active', 'manufacturer']
    search_fields = ['name', 'ip', 'api_device_id']
```

**Action Items:**
- [ ] Add `status` to list_display
- [ ] Add `status` to list_filter
- [ ] Add color coding for status (list_display method)
- [ ] Test filtering and searching

### 4. API Endpoint Integration

**Files to Update:**
- [ ] `micboard/api/v1/viewsets.py` - Add transition endpoints

**Tasks:**

#### 4.1 Add Lifecycle Action Endpoints

**Example:**
```python
from rest_framework.decorators import action
from micboard.services.device_lifecycle import get_lifecycle_manager

class ReceiverViewSet(viewsets.ModelViewSet):
    @action(detail=True, methods=['post'])
    def mark_online(self, request, pk=None):
        receiver = self.get_object()
        lifecycle = get_lifecycle_manager(receiver.manufacturer.code)

        if lifecycle.mark_online(receiver):
            return Response({'status': 'success', 'device_status': receiver.status})
        return Response({'status': 'error'}, status=400)

    @action(detail=True, methods=['post'])
    def maintenance_mode(self, request, pk=None):
        receiver = self.get_object()
        reason = request.data.get('reason', 'API request')
        lifecycle = get_lifecycle_manager(receiver.manufacturer.code)

        if lifecycle.mark_maintenance(receiver, reason=reason):
            return Response({'status': 'success', 'device_status': receiver.status})
        return Response({'status': 'error'}, status=400)

    @action(detail=True, methods=['post'])
    def sync_to_api(self, request, pk=None):
        receiver = self.get_object()
        service = get_service(receiver.manufacturer.code)
        fields = request.data.get('fields', None)

        if service.sync_device_to_api(receiver, fields=fields):
            return Response({'status': 'success', 'synced': True})
        return Response({'status': 'error', 'synced': False}, status=400)
```

**Action Items:**
- [ ] Add `mark_online` endpoint
- [ ] Add `mark_offline` endpoint
- [ ] Add `mark_degraded` endpoint
- [ ] Add `maintenance_mode` endpoint
- [ ] Add `sync_to_api` endpoint
- [ ] Test with curl/httpie
- [ ] Document in API docs

### 5. Testing Suite

**Create Test Files:**
- [ ] `tests/test_device_lifecycle.py` - Unit tests
- [ ] `tests/test_shure_service.py` - Integration tests
- [ ] `tests/test_lifecycle_api.py` - API endpoint tests

**Tasks:**

#### 5.1 Unit Tests

**File:** `tests/test_device_lifecycle.py`

```python
import pytest
from micboard.services.device_lifecycle import DeviceLifecycleManager, DeviceStatus
from micboard.models import Receiver

@pytest.mark.django_db
class TestDeviceLifecycleManager:
    def test_valid_transition(self, receiver):
        manager = DeviceLifecycleManager('shure')
        receiver.status = DeviceStatus.DISCOVERED.value

        assert manager.transition_device(receiver, DeviceStatus.PROVISIONING.value)
        receiver.refresh_from_db()
        assert receiver.status == DeviceStatus.PROVISIONING.value

    def test_invalid_transition(self, receiver):
        manager = DeviceLifecycleManager('shure')
        receiver.status = DeviceStatus.RETIRED.value

        assert not manager.transition_device(receiver, DeviceStatus.ONLINE.value)
        receiver.refresh_from_db()
        assert receiver.status == DeviceStatus.RETIRED.value

    def test_health_check_offline(self, receiver):
        from datetime import timedelta
        from django.utils import timezone

        manager = DeviceLifecycleManager('shure')
        receiver.status = DeviceStatus.ONLINE.value
        receiver.last_seen = timezone.now() - timedelta(minutes=10)
        receiver.save()

        status = manager.check_device_health(receiver, threshold_minutes=5)
        receiver.refresh_from_db()
        assert status == 'offline'
        assert receiver.status == DeviceStatus.OFFLINE.value
```

**Action Items:**
- [ ] Write tests for all transition methods
- [ ] Test invalid transitions
- [ ] Test health checks
- [ ] Test bi-directional sync (with mocked API)
- [ ] Test bulk operations

#### 5.2 Integration Tests

**File:** `tests/test_shure_service.py`

```python
import pytest
from unittest.mock import Mock, patch
from micboard.services.manufacturer_service import get_service

@pytest.mark.django_db
class TestShureService:
    @patch('micboard.integrations.shure.ShureClient')
    def test_poll_devices(self, mock_client, manufacturer, receiver):
        mock_client.return_value.list_devices.return_value = [
            {
                'id': receiver.api_device_id,
                'name': 'Test Receiver',
                'state': 'ONLINE',
                'ip': str(receiver.ip),
            }
        ]

        service = get_service('shure')
        devices = service.poll_devices()

        assert len(devices) == 1
        receiver.refresh_from_db()
        assert receiver.status == 'online'

    def test_bi_directional_sync(self, receiver, service):
        # Update locally
        receiver.name = 'Updated Name'
        receiver.save()

        # Push to API (mocked)
        with patch.object(service.get_client(), 'update_device') as mock_update:
            mock_update.return_value = True
            assert service.sync_device_to_api(receiver, fields=['name'])
```

**Action Items:**
- [ ] Test poll_devices with mocked API
- [ ] Test device creation/update flow
- [ ] Test health monitoring
- [ ] Test error handling
- [ ] Test sync to API

#### 5.3 API Endpoint Tests

**File:** `tests/test_lifecycle_api.py`

```python
import pytest
from rest_framework.test import APIClient

@pytest.mark.django_db
class TestLifecycleAPI:
    def test_mark_online_endpoint(self, api_client, receiver, user):
        api_client.force_authenticate(user=user)

        response = api_client.post(f'/api/v2/receivers/{receiver.pk}/mark_online/')

        assert response.status_code == 200
        assert response.data['status'] == 'success'
        receiver.refresh_from_db()
        assert receiver.status == 'online'

    def test_maintenance_mode_endpoint(self, api_client, receiver, user):
        api_client.force_authenticate(user=user)

        response = api_client.post(
            f'/api/v2/receivers/{receiver.pk}/maintenance_mode/',
            {'reason': 'Testing'}
        )

        assert response.status_code == 200
        receiver.refresh_from_db()
        assert receiver.status == 'maintenance'
```

**Action Items:**
- [ ] Test all lifecycle endpoints
- [ ] Test permissions
- [ ] Test error cases
- [ ] Test response formats

### 6. Documentation Updates

**Files to Create/Update:**
- [ ] `docs/api/lifecycle-endpoints.md` - API documentation
- [ ] `docs/admin-guide.md` - Admin user guide
- [ ] `README.md` - Update with lifecycle info

**Tasks:**

**Action Items:**
- [ ] Document all API endpoints
- [ ] Document admin actions
- [ ] Update README with lifecycle features
- [ ] Add code examples
- [ ] Update architecture diagrams

## Verification Steps

### End-to-End Test Scenario

```bash
# 1. Start services
python manage.py runserver

# 2. Configure discovery (if needed)
python manage.py shell
>>> from micboard.services.manufacturer_service import get_service
>>> service = get_service('shure')
>>> service.configure_discovery(['192.168.1.0/24'])

# 3. Run polling
python manage.py poll_devices

# 4. Check results
python manage.py shell
>>> from micboard.models import Receiver
>>> receivers = Receiver.objects.all()
>>> for r in receivers:
...     print(f'{r.name}: {r.status} (active={r.is_active})')

# 5. Test admin action
# Visit http://localhost:8000/admin/micboard/receiver/
# Select devices → Actions → "Put in maintenance mode"

# 6. Test API endpoint
curl -X POST http://localhost:8000/api/v2/receivers/1/mark_online/ \
  -H "Authorization: Token YOUR_TOKEN"

# 7. Check WebSocket
# Open browser console on dashboard
# Trigger status change and watch for WebSocket messages
```

## Rollback Plan

If issues arise:

```bash
# 1. Revert migration
python manage.py migrate micboard 0005

# 2. Checkout previous code
git checkout <previous-commit>

# 3. Restart services
python manage.py runserver
```

**Backup Before Integration:**
```bash
# Database backup
python manage.py dumpdata micboard > backup_before_lifecycle.json

# Code snapshot
git commit -am "Pre-lifecycle integration checkpoint"
git tag pre-lifecycle-integration
```

## Success Criteria

- [ ] All existing Shure devices transition correctly
- [ ] Polling command uses lifecycle manager
- [ ] WebSocket broadcasts work in real-time
- [ ] Admin actions function properly
- [ ] API endpoints respond correctly
- [ ] All tests pass (unit + integration)
- [ ] No regressions in existing functionality
- [ ] Documentation complete and accurate

## Timeline Estimate

- **Task 1 (Shure Integration):** 2-3 hours
- **Task 2 (WebSocket Testing):** 1 hour
- **Task 3 (Admin Interface):** 1-2 hours
- **Task 4 (API Endpoints):** 1-2 hours
- **Task 5 (Testing Suite):** 3-4 hours
- **Task 6 (Documentation):** 1-2 hours

**Total Estimated Time:** 9-14 hours

## Notes

- Start with Task 1 (Shure Integration) as foundation
- Test thoroughly at each step
- Keep backup checkpoints
- Document any issues encountered
- Update this checklist as you progress
