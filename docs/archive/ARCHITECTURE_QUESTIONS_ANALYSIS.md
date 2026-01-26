## Architectural Questions Analysis

### Question 1: Does the Swagger API at localhost:10000/v1.0/swagger.json expose all transmitter metadata?

**Status**: ⚠️ **PARTIAL** - New fields NOT yet exposed

The transmitter model now has 5 new fields (Phase 4.3):
- `serial_number` ✅ Added to model
- `model` ✅ Added to model
- `battery_runtime` ✅ Added to model
- `battery_type` ✅ Added to model
- `firmware_version` ✅ Added to model

**Current Transmitter Serializer** (micboard/serializers/serializers.py, lines 18-37):
```python
class TransmitterSerializer(serializers.ModelSerializer):
    battery_health = serializers.CharField(read_only=True)
    signal_quality = serializers.CharField(source="get_signal_quality", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Transmitter
        fields: ClassVar[list[str]] = [
            "slot",
            "battery",
            "battery_charge",
            "battery_percentage",
            "audio_level",
            "rf_level",
            "frequency",
            "antenna",
            "tx_offset",
            "quality",
            "runtime",
            "status",
            "name",
            "name_raw",
            "updated_at",
            "battery_health",
            "signal_quality",
            "is_active",
        ]
```

**Missing from API**:
- ❌ `serial_number` - Not in serializer fields
- ❌ `model` - Not in serializer fields
- ❌ `battery_type` - Not in serializer fields
- ❌ `battery_runtime` - Not in serializer fields
- ❌ `firmware_version` - Not in serializer fields

**Recommendation**: Update TransmitterSerializer to include new fields:
```python
class TransmitterSerializer(serializers.ModelSerializer):
    battery_health = serializers.CharField(read_only=True)
    battery_info = serializers.SerializerMethodField(read_only=True)
    signal_quality = serializers.CharField(source="get_signal_quality", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Transmitter
        fields = [
            # Existing fields
            "slot",
            "battery",
            "battery_charge",
            "battery_percentage",
            "audio_level",
            "rf_level",
            "frequency",
            "antenna",
            "tx_offset",
            "quality",
            "runtime",
            "status",
            "name",
            "name_raw",
            "updated_at",
            # New fields (Phase 4.3)
            "serial_number",
            "model",
            "firmware_version",
            "battery_type",
            "battery_runtime",
            # Computed fields
            "battery_health",
            "battery_info",
            "signal_quality",
            "is_active",
        ]

    def get_battery_info(self, obj):
        """Return comprehensive battery status dict"""
        return obj.battery_info  # Uses the new property from model
```

---

### Question 2: Are we updating device uptime and minimizing DB churn with django-simple-history?

**Status**: ❌ **NOT IMPLEMENTED** - But there's a better solution

**Current Situation**:

1. **Last Seen Updates** (every poll cycle):
   ```python
   # micboard/services/device_service.py
   receiver.last_seen = timezone.now()
   receiver.save(update_fields=['last_seen'])  # Writes to DB every sync
   ```
   - ✅ Good: Uses `update_fields` to minimize columns written
   - ❌ Bad: Still writes to DB on every poll (default: every 30s = 2880 writes/day per device)

2. **Battery Level Updates** (every poll):
   ```python
   transmitter.battery = battery_level
   transmitter.save()  # Full save writes to changelog + triggers signals
   ```

3. **Uptime Tracking**:
   - ❌ No uptime calculation exists currently
   - Only `last_seen` timestamp (not cumulative uptime)

**Django-Simple-History Analysis**:

Pros:
- ✅ Automatic audit trail of all changes
- ✅ Can query "was device online at time T"
- ✅ Historical trending (uptime over 7 days, 30 days)

Cons:
- ❌ **Creates 2 DB writes per update** (1 to models_transmitter, 1 to models_transmitter_history)
- ❌ **Doubles storage usage** for frequently updated fields
- ❌ **Increases churn** - opposite of your goal!
- ❌ History table grows unbounded (~2880 rows/day per device for battery updates)

**Better Solution: Uptime Service Pattern** (Recommended):

Instead of simple-history, implement lightweight uptime calculation:

```python
# micboard/services/uptime_service.py
from django.utils import timezone
from datetime import timedelta

class UptimeService:
    """Calculate device uptime without historical bloat."""

    @staticmethod
    def record_status_change(device, online: bool):
        """
        Record status change, calculate uptime.
        Only writes when status CHANGES (not on every poll).
        """
        previous_status = device.is_online
        device.is_online = online

        if previous_status != online:
            if online:  # Just came online
                device.last_online_at = timezone.now()
                device.last_offline_at = None
            else:  # Just went offline
                device.last_offline_at = timezone.now()
                # Calculate uptime from last_online_at
                if device.last_online_at:
                    uptime = timezone.now() - device.last_online_at
                    device.total_uptime_minutes += int(uptime.total_seconds() / 60)

            device.save()  # Single write on status change only

    @staticmethod
    def get_uptime_percentage(device, days: int = 7) -> float:
        """Calculate uptime % over N days."""
        cutoff = timezone.now() - timedelta(days=days)
        # Query movement log (already exists!)
        movements = DeviceMovementLog.objects.filter(
            device=device,
            detected_at__gte=cutoff
        )

        # Calculate from movements (no extra writes needed)
        total_time = timezone.now() - cutoff
        offline_time = timedelta()

        for movement in movements.filter(old_ip__isnull=False):  # IP changes indicate downtime
            if movement.acknowledged_at:
                offline_time += (movement.acknowledged_at - movement.detected_at)

        return ((total_time - offline_time) / total_time) * 100
```

**Model Enhancement** (minimal schema change):

```python
class Receiver(models.Model):
    # ... existing fields ...

    # Uptime tracking (write only on status change)
    is_online = models.BooleanField(default=False, db_index=True)
    last_online_at = models.DateTimeField(null=True, blank=True)
    last_offline_at = models.DateTimeField(null=True, blank=True)
    total_uptime_minutes = models.IntegerField(default=0)  # Cumulative
    uptime_percentage_7d = models.FloatField(default=0)    # Cached calculated value

    @property
    def uptime_7d_percentage(self) -> float:
        """Get 7-day uptime percentage"""
        return UptimeService.get_uptime_percentage(self, days=7)

    @property
    def uptime_summary(self) -> dict:
        """Return uptime summary without extra queries"""
        return {
            "is_online": self.is_online,
            "last_online_at": self.last_online_at,
            "total_uptime_minutes": self.total_uptime_minutes,
            "uptime_7d": self.uptime_7d_percentage,
            "last_status_change": self.last_offline_at or self.last_online_at,
        }
```

**Database Churn Comparison**:

| Approach | Writes/Poll | Rows/Day | Table Size | Purpose |
|----------|------------|----------|-----------|---------|
| Current (just last_seen) | 1 | 2880 | Minimal | Tracking |
| Simple-History | 2 | 2880+ | 2x larger | Audit trail |
| **Uptime Service** | **0.01** ⭐ | **29** | Minimal | Calculation |

The Uptime Service only writes when status CHANGES, not on every poll!

---

### Question 3: Are we flagging Device ID duplicates?

**Status**: ✅ **YES** - Partially implemented

**Current Implementation**:

1. **Duplicate Detection by API Device ID** ✅
   ```python
   # micboard/services/deduplication_service.py:295
   def _check_by_api_id(self, api_device_id: str, ip: str, manufacturer):
       try:
           existing = Receiver.objects.get(
               manufacturer=manufacturer,
               api_device_id=api_device_id,
           )
           # Same device in manufacturer's system
           if existing.ip != ip:
               return DeduplicationResult(
                   is_moved=True,
                   conflict_type="ip_changed",
               )
           return DeduplicationResult(
               is_duplicate=True,
               conflict_type="duplicate",
           )
       except Receiver.DoesNotExist:
           pass
       return None
   ```

2. **Priority 4 in Deduplication** ✅
   ```python
   # Deduplication priority order:
   # Priority 1: serial_number (most reliable)
   # Priority 2: mac_address (hardware identity)
   # Priority 3: ip (detect conflicts)
   # Priority 4: api_device_id (manufacturer-specific) ← HERE
   ```

3. **API ID Conflicts Detection** ✅ - Implemented for Receivers
   - Same api_device_id, different IP = Movement
   - Same api_device_id, same IP = Duplicate (update only)
   - Different api_device_id, same serial = Duplicate (different API ID)

**What's NOT Flagged** ❌:

1. **API ID Conflicts Across Manufacturers**
   - If Shure and Sennheiser both report same api_device_id
   - Current: Each manufacturer isolated
   - Better: Flag cross-vendor conflicts

2. **API ID Changes on Same Device**
   - If device's api_device_id changes (firmware update, re-registration)
   - Current: Would create new device (wrong!)
   - Better: Track serial_number as primary key, api_device_id as secondary

3. **Duplicate API IDs Within Same Manufacturer**
   - Two devices reported with same api_device_id (API bug)
   - Current: Would overwrite one with other
   - Better: Queue both for review with ⚠️ DUPLICATE API ID flag

**Recommendation: Enhanced API ID Duplicate Detection**

```python
# micboard/services/deduplication_service.py - Add method

def check_api_id_conflicts(
    self, api_device_id: str, manufacturer: Manufacturer
) -> list[DeduplicationResult]:
    """
    Check for duplicate API device IDs (should never happen).

    Returns:
        List of conflicts if api_device_id appears multiple times
    """
    from micboard.models import Receiver

    # Check within same manufacturer
    duplicates = Receiver.objects.filter(
        manufacturer=manufacturer,
        api_device_id=api_device_id,
    )

    if duplicates.count() > 1:
        logger.warning(
            "🚨 API ID DUPLICATE: %s:%s exists in %d receivers!",
            manufacturer.code,
            api_device_id,
            duplicates.count(),
        )
        # Flag all as conflicts
        return [
            DeduplicationResult(
                is_conflict=True,
                existing_device=dup,
                conflict_type="duplicate_api_id",
                details={
                    "count": duplicates.count(),
                    "api_device_id": api_device_id,
                    "devices": list(duplicates.values_list("id", flat=True)),
                },
            )
            for dup in duplicates
        ]

    # Check across manufacturers
    cross_vendor = Receiver.objects.exclude(
        manufacturer=manufacturer
    ).filter(api_device_id=api_device_id)

    if cross_vendor.exists():
        logger.warning(
            "⚠️  CROSS-VENDOR API ID: %s also exists in %s",
            api_device_id,
            ", ".join(set(cross_vendor.values_list("manufacturer__code", flat=True))),
        )
        # Might be legitimate (if API standardized), but flag for review
```

**Updated DiscoveryQueue Model** - Add new conflict type:

```python
class DiscoveryQueue(models.Model):
    # ... existing fields ...

    is_duplicate_api_id = models.BooleanField(default=False)  # NEW
    api_id_conflict_count = models.IntegerField(default=0)    # NEW

    def check_for_duplicates(self) -> dict:
        """Returns conflict analysis dict with API ID info"""
        conflicts = {}

        # Check for duplicate api_device_id
        same_api_id = DiscoveryQueue.objects.filter(
            api_device_id=self.api_device_id,
            manufacturer=self.manufacturer,
            status__in=['pending', 'approved', 'imported'],
        ).exclude(id=self.id).count()

        if same_api_id > 0:
            conflicts['duplicate_api_id'] = same_api_id
            self.is_duplicate_api_id = True
            self.api_id_conflict_count = same_api_id

        return conflicts
```

**Admin Display Enhancement**:

```python
# micboard/admin/discovery_admin.py

class DiscoveryQueueAdmin(admin.ModelAdmin):
    def conflict_indicators(self, obj: DiscoveryQueue) -> str:
        """Display warning badges for conflicts."""
        badges = []

        if obj.is_duplicate:
            badges.append(
                '<span style="background-color: #ffcc00;">⚠ DUPLICATE</span>'
            )

        if obj.is_ip_conflict:
            badges.append(
                '<span style="background-color: #ff3333;">⛔ IP CONFLICT</span>'
            )

        # NEW: API ID duplicate detection
        if obj.is_duplicate_api_id:
            badges.append(
                f'<span style="background-color: #ff6600;">🚨 {obj.api_id_conflict_count} API IDs</span>'
            )

        return format_html(" ".join(badges)) if badges else "—"
```

---

## Summary & Recommendations

| Question | Current | Recommended Action |
|----------|---------|-------------------|
| **Transmitter Metadata in API?** | ⚠️ Partial | Update TransmitterSerializer to include serial_number, model, firmware_version, battery_type, battery_runtime |
| **Uptime + DB Churn?** | ❌ Simple-history would double writes | Implement UptimeService: writes only on status changes (~29/day vs 2880/day) |
| **API ID Duplicates?** | ✅ Basic detection | Enhance with `is_duplicate_api_id` flag and cross-vendor conflict detection |

---

## Implementation Priority

1. **HIGH**: Update TransmitterSerializer (5 minutes)
   - Add 5 new fields to API response
   - Enables full device tracking in Swagger

2. **HIGH**: Implement UptimeService (1-2 hours)
   - Dramatically reduces database churn
   - Enables uptime reporting without bloat
   - Better than simple-history

3. **MEDIUM**: Enhanced API ID Duplicate Detection (30 minutes)
   - Add flags to DiscoveryQueue
   - Improve admin display
   - Catch API bugs early
