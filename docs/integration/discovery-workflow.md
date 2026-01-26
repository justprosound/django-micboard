# Device Discovery Workflow

## Overview

Django-micboard implements a comprehensive device discovery and deduplication system that maintains an authoritative registry of wireless microphone equipment across multi-vendor networks. The system detects new devices, tracks movements, identifies conflicts, and provides an approval workflow for manual review.

## Architecture

```
┌──────────────────────────┐
│  Manufacturer APIs       │
│  (Shure, Sennheiser)     │
└────────────┬─────────────┘
             │ API polling (poll_devices)
             ▼
┌──────────────────────────┐
│ DeviceDeduplicationService│
│  • Priority matching      │
│  • Conflict detection     │
│  • Movement tracking      │
└────────────┬─────────────┘
             │
      ┌──────┴──────┐
      ▼             ▼
┌──────────┐  ┌──────────────┐
│ Receiver │  │ DiscoveryQueue│
│  Models  │  │  (staging)    │
└──────────┘  └──────────────┘
      │             │
      └──────┬──────┘
             ▼
    ┌──────────────────┐
    │DeviceMovementLog │
    │  (audit trail)   │
    └──────────────────┘
```

## Deduplication Priority

The system uses a four-tier priority matching algorithm to identify devices:

### Priority 1: Serial Number (Most Reliable)
- **Field**: `serial_number`
- **Source**: Manufacturer API (e.g., Shure firmware reports)
- **Reliability**: Highest - unique hardware identifier
- **Use Case**: Primary deduplication key

```python
# Example: Shure ULXD4D with serial
{
    "serial_number": "TEST-001",
    "mac_address": "00:0e:dd:4c:43:78",
    "ip": "172.21.2.140"
}
```

### Priority 2: MAC Address (Hardware Identity)
- **Field**: `mac_address`
- **Source**: Network interface (ARP/DHCP/API)
- **Reliability**: High - unique network hardware
- **Use Case**: Fallback when serial unavailable

```python
# Example: Device without serial in API
{
    "mac_address": "00:0e:dd:4c:43:78",
    "ip": "172.21.2.140"
}
```

### Priority 3: IP Address (Location)
- **Field**: `ip`
- **Source**: Network configuration
- **Reliability**: Medium - can change with DHCP
- **Use Case**: Detect IP conflicts

```python
# Detects conflict when different device uses same IP
existing_device = {
    "serial_number": "TEST-001",
    "ip": "172.21.2.140"
}
new_device = {
    "serial_number": "TEST-002",  # Different device!
    "ip": "172.21.2.140"  # Same IP = conflict
}
```

### Priority 4: API Device ID (Manufacturer-Specific)
- **Field**: `api_device_id`
- **Source**: Manufacturer's internal ID (e.g., Shure GUID)
- **Reliability**: Variable - can change with firmware
- **Use Case**: Last resort matching

## Conflict Types

### 1. Device Movement (IP Changed)
**Detection**: Same serial/MAC, different IP
**Action**: Update IP, log movement
**Status**: Auto-resolved with audit log

```python
# Before
receiver = Receiver(serial_number="TEST-001", ip="192.168.1.100")

# After discovery
# Detected: Same device, new IP
# Action: Update IP to 192.168.1.200
# Log: DeviceMovementLog created
```

**Admin View**:
```
Device: TEST-001
Movement: IP 192.168.1.100 → 192.168.1.200
Status: ⚠ PENDING ACKNOWLEDGMENT
```

### 2. IP Conflict (Different Device, Same IP)
**Detection**: Different serial/MAC, same IP
**Action**: Queue for manual review
**Status**: Requires admin approval

```python
# Existing device
receiver_a = Receiver(serial_number="TEST-001", ip="192.168.1.100")

# New discovery
device_b = {
    "serial_number": "TEST-002",  # Different device
    "ip": "192.168.1.100"  # Same IP!
}
# → Queued to DiscoveryQueue with is_ip_conflict=True
```

**Admin View**:
```
Device: TEST-002
IP: 192.168.1.100
Conflict: ⛔ IP CONFLICT
Existing Device: TEST-001 (also at 192.168.1.100)
Status: Pending Review
```

### 3. Manufacturer Mismatch
**Detection**: Same serial, different manufacturer
**Action**: Queue for review (likely duplicate serial across vendors)
**Status**: Requires admin approval

### 4. Duplicate Device
**Detection**: Exact match on serial/MAC/API ID
**Action**: Update metadata, refresh last_seen
**Status**: Auto-resolved

## Discovery Queue States

The `DiscoveryQueue` model manages staged devices with the following workflow:

```
pending → approved → imported
   ↓         ↓
rejected   duplicate
```

### State Descriptions

| State       | Description                          | Next Actions                      |
|-------------|--------------------------------------|-----------------------------------|
| `pending`   | Awaiting admin review                | Approve, Reject, Mark Duplicate   |
| `approved`  | Admin approved, ready for import     | Auto-import to Receiver           |
| `rejected`  | Admin rejected device                | Remove from queue                 |
| `imported`  | Successfully imported to Receiver    | Link to created device            |
| `duplicate` | Marked as duplicate, skip import     | Keep for audit trail              |

## Admin Workflow

### 1. Viewing Discovered Devices

Navigate to **Admin > Micboard > Discovery Queue**

**List Filters**:
- Status (pending, approved, rejected, imported, duplicate)
- Manufacturer (Shure, Sennheiser, etc.)
- Device Type (receiver, transmitter)
- Conflict Flags (is_duplicate, is_ip_conflict)
- Discovered Date

**List Display**:
```
Name              | Manufacturer | Serial      | IP            | Status   | Conflicts        | Discovered
------------------|--------------|-------------|---------------|----------|------------------|------------
ULX-D Quad        | Shure        | TEST-001    | 172.21.2.140 | PENDING  | ⚠ DUPLICATE     | 2025-01-22
ULXD4D            | Shure        | TEST-002    | 172.21.2.141 | PENDING  | ⛔ IP CONFLICT  | 2025-01-22
SK 6000           | Sennheiser   | SN-5678     | 10.0.1.50    | APPROVED | —                | 2025-01-22
```

### 2. Reviewing Conflict Details

Click on a device to view detailed conflict analysis:

```
Device Information:
  Name: ULXD4D
  Serial Number: TEST-002
  MAC Address: 00:0e:dd:4c:43:78
  IP: 172.21.2.141

Conflict Analysis:
  ⛔ IP Conflict Detected
  existing_device: TEST-001 (Shure Receiver at 172.21.2.141)
  conflict_type: ip_conflict
  details: Different device using same IP address
```

### 3. Approving Devices

**Action**: Select devices → **Actions dropdown** → **Approve selected devices for import**

This will:
1. Create `Receiver` object with all metadata
2. Set status to `imported`
3. Link `existing_device` to created receiver
4. Set `reviewed_by` to current admin user
5. Show success message: "Approved and imported 3 device(s)."

### 4. Rejecting Devices

**Action**: Select devices → **Actions dropdown** → **Reject selected devices**

This will:
1. Set status to `rejected`
2. Prevent auto-import
3. Keep record for audit trail

### 5. Acknowledging Movements

Navigate to **Admin > Micboard > Device Movement Log**

**List Display**:
```
Device      | Manufacturer | Movement                                 | Detected    | Status
------------|--------------|------------------------------------------|-------------|---------------------
TEST-001    | Shure        | IP: 192.168.1.100 → 192.168.1.200       | 2025-01-22  | ⚠ PENDING
TEST-003    | Shure        | Location: Studio A → Studio B            | 2025-01-22  | ✓ ACKNOWLEDGED
```

**Action**: Select movements → **Actions dropdown** → **Acknowledge selected movements**

## Example Scenarios

### Scenario 1: New Device Discovery

**API Data** (Shure ULXD4D):
```json
{
    "api_device_id": "guog244",
    "serial_number": "ULXD4D-12345",
    "mac_address": "00:0e:dd:4c:43:78",
    "ip": "172.21.2.140",
    "subnet_mask": "255.255.255.0",
    "gateway": "172.21.0.1",
    "model": "ULXD4D",
    "firmware_version": "2.7.6.0",
    "hosted_firmware_version": "2.7.3.0",
    "interface_id": "0.6.0"
}
```

**Deduplication Result**:
- Priority 1 (Serial): No match
- Priority 2 (MAC): No match
- Priority 3 (IP): No match
- Priority 4 (API ID): No match
- **Result**: `is_new=True`

**Action**: Create new `Receiver` with all metadata:
```python
receiver = Receiver.objects.create(
    manufacturer=manufacturer,
    api_device_id="guog244",
    serial_number="ULXD4D-12345",
    mac_address="00:0e:dd:4c:43:78",
    ip="172.21.2.140",
    subnet_mask="255.255.255.0",
    gateway="172.21.0.1",
    model="ULXD4D",
    firmware_version="2.7.6.0",
    hosted_firmware_version="2.7.3.0",
    interface_id="0.6.0",
)
```

### Scenario 2: Device Movement Detection

**Existing Device**:
```python
receiver = Receiver(
    serial_number="ULXD4D-12345",
    ip="172.21.2.140"
)
```

**New API Data** (same device, new IP):
```json
{
    "serial_number": "ULXD4D-12345",  # Same serial
    "ip": "172.21.3.100"  # New IP!
}
```

**Deduplication Result**:
- Priority 1 (Serial): Match! But IP changed.
- **Result**: `is_moved=True`, `conflict_type="ip_changed"`

**Actions**:
1. Update receiver IP: `receiver.ip = "172.21.3.100"`
2. Create `DeviceMovementLog`:
   ```python
   DeviceMovementLog.objects.create(
       device=receiver,
       old_ip="172.21.2.140",
       new_ip="172.21.3.100",
       detected_by="sync",
       reason="Detected during shure sync",
       acknowledged=False,
   )
   ```
3. Admin sees: **⚠ PENDING** acknowledgment in movement log

### Scenario 3: IP Conflict

**Existing Device A**:
```python
receiver_a = Receiver(
    serial_number="DEVICE-A",
    ip="192.168.1.100"
)
```

**New API Data** (Device B, same IP):
```json
{
    "serial_number": "DEVICE-B",  # Different device
    "mac_address": "AA:BB:CC:DD:EE:FF",  # Different MAC
    "ip": "192.168.1.100"  # Same IP as Device A!
}
```

**Deduplication Result**:
- Priority 1 (Serial): No match (different serial)
- Priority 2 (MAC): No match (different MAC)
- Priority 3 (IP): **Match! But serial/MAC differ.**
- **Result**: `is_conflict=True`, `conflict_type="ip_conflict"`

**Actions**:
1. **Do NOT auto-create** receiver
2. Create `DiscoveryQueue` entry:
   ```python
   DiscoveryQueue.objects.create(
       manufacturer=manufacturer,
       serial_number="DEVICE-B",
       mac_address="AA:BB:CC:DD:EE:FF",
       ip="192.168.1.100",
       status="pending",
       is_ip_conflict=True,
       existing_device=receiver_a,  # Link to conflicting device
   )
   ```
3. Admin sees: **⛔ IP CONFLICT** badge in discovery queue
4. Admin reviews and decides:
   - **Option A**: Reject (network misconfiguration)
   - **Option B**: Approve (Device A moved, Device B legit)

## Integration with poll_devices

The deduplication service is integrated into the polling command:

```python
# micboard/management/commands/poll_devices.py

for manufacturer in Manufacturer.objects.filter(api_enabled=True):
    service = get_device_service(manufacturer)
    created, updated = service.sync_devices_from_api()

    # sync_devices_from_api now uses DeviceDeduplicationService:
    # 1. Fetches device list from API
    # 2. For each device:
    #    a. Extract serial, MAC, IP, network metadata
    #    b. Call dedup_service.check_device()
    #    c. Handle result (new/duplicate/moved/conflict)
    # 3. Returns (created_count, updated_count)
```

## API Endpoints

### Get Pending Approvals

```http
GET /api/discovery/pending/
```

**Response**:
```json
{
  "count": 2,
  "results": [
    {
      "id": 1,
      "manufacturer": "Shure",
      "serial_number": "TEST-001",
      "ip": "172.21.2.140",
      "status": "pending",
      "is_duplicate": false,
      "is_ip_conflict": true,
      "discovered_at": "2025-01-22T15:30:00Z"
    }
  ]
}
```

### Get Unacknowledged Movements

```http
GET /api/movements/unacknowledged/
```

**Response**:
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "device": {
        "id": 5,
        "name": "ULXD4D Receiver",
        "serial_number": "TEST-001"
      },
      "old_ip": "192.168.1.100",
      "new_ip": "192.168.1.200",
      "movement_type": "ip_only",
      "detected_at": "2025-01-22T15:30:00Z",
      "acknowledged": false
    }
  ]
}
```

## Database Schema

### Receiver (Enhanced)

| Field                      | Type         | Description                         |
|----------------------------|--------------|-------------------------------------|
| `serial_number`            | CharField    | **[Indexed]** Hardware serial       |
| `mac_address`              | CharField    | **[Indexed]** Network MAC address   |
| `ip`                       | GenericIPAddress | Device IP address              |
| `subnet_mask`              | GenericIPAddress | Network subnet                 |
| `gateway`                  | GenericIPAddress | Network gateway                |
| `network_mode`             | CharField    | auto/manual/dhcp/static             |
| `interface_id`             | CharField    | Network interface version           |
| `model`                    | CharField    | Manufacturer model (e.g., ULXD4D)   |
| `description`              | TextField    | Device description                  |
| `firmware_version`         | CharField    | Device firmware version             |
| `hosted_firmware_version`  | CharField    | Transmitter firmware (for receivers)|

### DiscoveryQueue

| Field              | Type          | Description                            |
|--------------------|---------------|----------------------------------------|
| `manufacturer`     | ForeignKey    | Manufacturer reference                 |
| `api_device_id`    | CharField     | Manufacturer device ID                 |
| `serial_number`    | CharField     | **[Indexed]** Hardware serial          |
| `mac_address`      | CharField     | Network MAC address                    |
| `ip`               | GenericIPAddress | **[Indexed]** Device IP             |
| `device_type`      | CharField     | receiver/transmitter                   |
| `status`           | CharField     | **[Indexed]** pending/approved/rejected|
| `is_duplicate`     | Boolean       | Duplicate device flag                  |
| `is_ip_conflict`   | Boolean       | IP conflict flag                       |
| `existing_device`  | ForeignKey    | Link to conflicting receiver           |
| `reviewed_by`      | ForeignKey    | Admin user who reviewed                |
| `discovered_at`    | DateTimeField | **[Indexed]** Discovery timestamp      |
| `metadata`         | JSONField     | Full API response                      |

### DeviceMovementLog

| Field              | Type          | Description                            |
|--------------------|---------------|----------------------------------------|
| `device`           | ForeignKey    | **[Indexed]** Receiver reference       |
| `old_ip`           | GenericIPAddress | Previous IP address                 |
| `new_ip`           | GenericIPAddress | New IP address                      |
| `old_location`     | ForeignKey    | Previous location                      |
| `new_location`     | ForeignKey    | New location                           |
| `detected_at`      | DateTimeField | **[Indexed]** Detection timestamp      |
| `detected_by`      | CharField     | Detection source (sync/manual)         |
| `reason`           | TextField     | Movement reason/description            |
| `acknowledged`     | Boolean       | **[Indexed]** Admin acknowledged flag  |
| `acknowledged_by`  | ForeignKey    | Admin user who acknowledged            |

## Performance Considerations

### Indexes

All deduplication keys are indexed for fast lookups:

```python
class Receiver(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['serial_number']),
            models.Index(fields=['mac_address']),
            models.Index(fields=['ip']),
            models.Index(fields=['api_device_id', 'manufacturer']),
        ]
```

### Query Optimization

Deduplication checks use `select_related()` and efficient queries:

```python
# Check by serial (single query)
existing = Receiver.objects.filter(
    serial_number=serial_number,
    manufacturer=manufacturer
).select_related('location').first()

# Priority cascade: serial → MAC → IP → API ID
# Stops at first match (no redundant queries)
```

## Testing

Run the deduplication test suite:

```bash
python scripts/test_deduplication.py
```

**Tests**:
1. ✅ New device detection
2. ✅ Duplicate detection (by serial number)
3. ✅ Device movement detection (IP change)
4. ✅ IP conflict detection
5. ✅ MAC address matching

**Expected Output**:
```
============================================================
Device Deduplication Service Test Suite
============================================================

=== Test 1: New Device Detection ===
  Is New: True
  ✓ PASSED

=== Test 2: Duplicate Detection (Serial Number) ===
  Is Duplicate: True
  ✓ PASSED

=== Test 3: Device Movement Detection (IP Change) ===
  Is Moved: True
  ✓ PASSED

=== Test 4: IP Conflict Detection ===
  Is Conflict: True
  ✓ PASSED

=== Test 5: MAC Address Matching ===
  Is Duplicate: True (matched by MAC)
  ✓ PASSED

============================================================
✅ ALL TESTS PASSED
============================================================
```

## Future Enhancements

### Phase 2 (Notifications)
- [ ] Email alerts for pending approvals
- [ ] Dashboard widget for unacknowledged movements
- [ ] Slack/Teams integration for conflict notifications
- [ ] Daily summary reports

### Phase 3 (Advanced Deduplication)
- [ ] Fuzzy matching for similar names
- [ ] Historical tracking (device seen at multiple IPs over time)
- [ ] Auto-approve patterns (trusted subnets, known devices)
- [ ] Bulk import from CSV with conflict detection

### Phase 4 (Multi-Manufacturer)
- [ ] Cross-manufacturer deduplication (same physical device, different APIs)
- [ ] Vendor-specific deduplication rules
- [ ] API priority (prefer Shure data over Sennheiser if conflict)

## Troubleshooting

### Issue: Devices Keep Getting Queued as Conflicts

**Cause**: API not returning serial numbers consistently

**Solution**: Check API response in `DiscoveryQueue.metadata` field:
```python
queue_item = DiscoveryQueue.objects.filter(status='pending').first()
print(queue_item.metadata)  # Full API response
```

If serial missing, check manufacturer API configuration.

### Issue: Device Moved But Not Detected

**Cause**: Serial number or MAC not populated

**Solution**: Ensure manufacturer plugin extracts identity fields:
```python
# micboard/manufacturers/shure/shure_plugin.py
def get_devices(self):
    return [
        {
            "id": device["id"],
            "serial_number": device.get("serialNumber"),  # Must extract
            "mac_address": device.get("macAddress"),      # Must extract
            "ip": device.get("ipAddress"),
        }
    ]
```

### Issue: Too Many Pending Approvals

**Cause**: Legitimate device movements queued as conflicts

**Solution**: Use "Approve" action to batch-import:
1. Select all pending items
2. Actions → "Approve selected devices for import"
3. Devices will be created and status set to `imported`

## References

- [Plugin Development](../archive/plugin-development.md) - Implementing manufacturer-specific extractors
- [Integration Architecture](../development/architecture.md) - System design and services
- [Rate Limiting](../archive/rate-limiting.md) - API polling rate limits
- [Integration References](integration-references.md) - API client configuration
