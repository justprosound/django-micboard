
# Service Layer Architecture

## High-Level Flow

```
┌────────────────────────────────────────────────────┐
│             External Entry Points                 │
├────────────────────────────────────────────────────┤
│  • REST API Views                                 │
│  • Django Management Commands                     │
│  • Django Signals                                 │
│  • Background Tasks (Django-Q)                    │
│  • WebSocket Consumers                            │
└────────────────┬─────────────────────────────────┘
                 │
                 ▼
        ┌────────────────────┐
        │  SERVICE LAYER     │
        │  (This Phase 1)    │
        └────────────────────┘
                 │
     ┌───────────┼───────────┬─────────────┬──────────┐
     │           │           │             │          │
     ▼           ▼           ▼             ▼          ▼
┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐
│ Device  │ │ Assign │ │Manufact. │ │Connect.  │ │Location│
│Service  │ │Service │ │Service   │ │ Service  │ │Service │
└────┬────┘ └───┬────┘ └──────┬───┘ └────┬─────┘ └───┬────┘
     │          │             │          │           │
     └──────────┼─────────────┼──────────┼───────────┘
                │
        ┌───────▼──────────┐
        │  DJANGO MODELS   │
        │  & DATABASE      │
        └──────────────────┘
                │
        ┌───────▼──────────────────┐
        │  Manufacturer APIs       │
        │  • Shure System API      │
        │  • Sennheiser SSCv2      │
        └──────────────────────────┘
```

## Service Responsibilities

### DeviceService
```
Receiver/Transmitter Models
    ▲
    │ sync_device_status()
    │ sync_device_battery()
    │ get_active_receivers()
    │ get_device_by_ip()
    │ search_devices()
    │ count_online_devices()
    │
┌───┴────────────────────┐
│   DeviceService        │
└────────────────────────┘
```

### AssignmentService
```
Assignment Model ◄─────┐
User Model             │ Association
Receiver Model         │
Transmitter Model ─────┘
    ▲
    │ create_assignment()
    │ update_assignment()
    │ get_user_assignments()
    │ get_users_with_alerts()
    │
┌───┴────────────────────┐
│ AssignmentService      │
└────────────────────────┘
```

### ManufacturerService
```
Configuration Model
    ▲
    │ sync_devices_for_manufacturer()
    │ test_manufacturer_connection()
    │ get_device_status()
    │
┌───┴────────────────────┐
│ ManufacturerService    │
├────────────────────────┤
│ • Gets plugins         │
│ • Calls APIs           │
│ • Updates models       │
└────────────────────────┘
    │
    ▼
Shure/Sennheiser APIs
```

### ConnectionHealthService
```
RealTimeConnection Model
    ▲
    │ create_connection()
    │ record_heartbeat()
    │ record_error()
    │ is_healthy()
    │ get_connection_stats()
    │ cleanup_stale_connections()
    │
┌───┴──────────────────────────┐
│ ConnectionHealthService      │
└──────────────────────────────┘
```

### LocationService
```
Location Model ◄──────────┐
Receiver Model ───────────┤ Relationships
Transmitter Model (future)─┘
    ▲
    │ create_location()
    │ assign_device_to_location()
    │ get_location_device_counts()
    │
┌───┴────────────────────┐
│   LocationService      │
└────────────────────────┘
```

### DiscoveryService
```
Discovery Model
    ▲
    │ create_discovery_task()
    │ execute_discovery()
    │ register_discovered_device()
    │
┌───┴────────────────────┐
│  DiscoveryService      │
└────────────────────────┘
```

## Method Categories by Service

### DeviceService (11 methods)

**Queries (5)**
```
get_active_receivers()
get_active_transmitters()
get_device_by_ip()
get_receivers_by_location()
get_transmitters_by_charger()
```

**Operations (3)**
```
sync_device_status()
sync_device_battery()
search_devices()
```

**Analytics (1)**
```
count_online_devices()
```

### AssignmentService (8 methods)

**CRUD (4)**
```
create_assignment()      # C: Creates with validation
update_assignment()      # U: Updates with selective fields
delete_assignment()      # D: Removes
get_user_assignments()   # R: Queries
```

**Queries (4)**
```
get_device_assignments()
get_users_with_alerts()
has_assignment()
```

### ManufacturerService (7 methods)

**Operations (2)**
```
sync_devices_for_manufacturer()    # Full sync
test_manufacturer_connection()      # Connectivity test
```

**Queries (4)**
```
get_plugin()
get_active_manufacturers()
get_manufacturer_config()
get_device_status()
```

### ConnectionHealthService (11 methods)

**Management (3)**
```
create_connection()
update_connection_status()
cleanup_stale_connections()
```

**Events (2)**
```
record_heartbeat()
record_error()
```

**Queries (4)**
```
get_active_connections()
get_unhealthy_connections()
get_connections_by_manufacturer()
is_healthy()
```

**Analytics (2)**
```
get_connection_stats()
get_connection_uptime()
```

### LocationService (9 methods)

**CRUD (4)**
```
create_location()      # C: Creates with validation
update_location()      # U: Updates with selective fields
delete_location()      # D: Removes
get_all_locations()    # R: Lists all
```

**Queries (3)**
```
get_location_by_name()
get_location_device_counts()
get_devices_in_location()
```

**Operations (2)**
```
assign_device_to_location()
unassign_device_from_location()
```

### DiscoveryService (9 methods)

**Task Management (4)**
```
create_discovery_task()
update_discovery_task()
delete_discovery_task()
get_enabled_discovery_tasks()
```

**Operations (2)**
```
execute_discovery()
register_discovered_device()
```

**Queries (2)**
```
get_discovery_results()
get_undiscovered_devices()
```

## Exception Flow

```
┌─────────────────────────────────────┐
│    Service Layer Operation          │
└──────────┬──────────────────────────┘
           │
      Validation checks
           │
    ┌──────┴──────┐
    │ Valid?      │
    ├──────┬──────┤
    │ YES  │ NO   │
    │      ▼      │
    │   Raise     │
    │  Exception  │
    │             │
    ▼    ┌────────▼───────────┐
  Execute │ Domain Exception   │
 Operation│ (MicboardService   │
          │  Error family)     │
          └────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  View/Command        │
        │  Catches & Handles   │
        └──────────────────────┘
```

## Data Flow Example: Device Sync

```
Management Command: poll_devices
         │
         ▼
ManufacturerService.sync_devices_for_manufacturer('shure')
         │
         ├─ Get plugin via get_manufacturer_plugin()
         │
         ├─ Call plugin.get_devices()
         │
         │ ┌─ For each device:
         │ │
         │ ├─ Find existing Receiver
         │ │
         │ ├─ Call DeviceService.sync_device_status()
         │ │
         │ ├─ Call DeviceService.sync_device_battery()
         │ │
         │ └─ Update Receiver model
         │
         └─ Return SyncResult {
              success: true,
              devices_added: 5,
              devices_updated: 3,
              devices_removed: 0,
              errors: []
            }
         │
         ▼
Command writes result to stdout
```

## Data Flow Example: User Assignment

```
REST API: POST /assignments
         │
         ▼
View receives request
         │
    ├─ Extract user from request
    ├─ Extract device from request.data
    │
    ▼
AssignmentService.create_assignment(
    user=user,
    device=device,
    alert_enabled=True
)
    │
    ├─ Check if Assignment exists
    │  ├─ YES → Raise AssignmentAlreadyExistsError
    │  └─ NO → Continue
    │
    ├─ Create Assignment model
    │
    └─ Return Assignment instance
         │
         ▼
View serializes Assignment
         │
         ▼
Return Response(serializer.data, status=201)
```

## Exception Hierarchy

```
MicboardServiceError (base)
│
├── DeviceNotFoundError
│   └── Raised by: DeviceService methods
│
├── AssignmentNotFoundError
│   └── Raised by: AssignmentService methods
│
├── AssignmentAlreadyExistsError
│   └── Raised by: AssignmentService.create_assignment()
│
├── LocationNotFoundError
│   └── Raised by: LocationService methods
│
├── LocationAlreadyExistsError
│   └── Raised by: LocationService.create_location()
│
├── ManufacturerPluginError
│   └── Raised by: ManufacturerService methods
│
├── DiscoveryError
│   └── Raised by: DiscoveryService methods
│
└── ConnectionError
    └── Raised by: ConnectionHealthService methods
```

## Dependency Graph

```
View Layer
    │
    ├─ DeviceService
    │   └─ Receiver/Transmitter Models
    │
    ├─ AssignmentService
    │   ├─ Assignment Model
    │   ├─ User Model
    │   └─ Receiver/Transmitter Models
    │
    ├─ ManufacturerService
    │   ├─ Configuration Model
    │   ├─ Manufacturer Plugins
    │   └─ Shure/Sennheiser APIs
    │
    ├─ ConnectionHealthService
    │   └─ RealTimeConnection Model
    │
    ├─ LocationService
    │   ├─ Location Model
    │   └─ Receiver/Transmitter Models
    │
    └─ DiscoveryService
        ├─ Discovery Model
        └─ Receiver/Transmitter Models
```

## Concurrency & State

```
Each Service Method is Stateless
│
├─ Static methods (no instance state)
│
├─ No caching at service layer
│
├─ Database provides consistency
│
└─ Caller responsible for:
   ├─ Transaction management
   ├─ Locking if needed
   └─ Batch operations
```

## Testing Architecture

```
┌──────────────────────────┐
│  Service Unit Tests      │
├──────────────────────────┤
│  Test each method        │
│  independently           │
│  Mock Django ORM         │
└──────────────────────────┘
           │
           ▼
┌──────────────────────────┐
│  View Integration Tests  │
├──────────────────────────┤
│  Mock services           │
│  Test HTTP layer         │
│  Verify error handling   │
└──────────────────────────┘
           │
           ▼
┌──────────────────────────┐
│  End-to-End Tests        │
├──────────────────────────┤
│  Real database           │
│  Real services           │
│  Real manufacturer API   │
│  (integration testing)   │
└──────────────────────────┘
```

## Performance Considerations

### Query Optimization
```
Services use Django ORM QuerySets
    │
    ├─ Lazy evaluation
    ├─ Can be filtered in calling code
    ├─ Supports .select_related()
    └─ Supports .prefetch_related()

Example:
devices = DeviceService.get_active_receivers()
         .select_related('location')
         .prefetch_related('assignments')
```

### Caching Strategy
```
Current (Phase 1):
    └─ No caching in services

Future (Phase 2):
    ├─ Optional cache decorator
    ├─ Redis-backed caching
    └─ Explicit cache control
```

### Bulk Operations
```
Current (Phase 1):
    └─ Single-record operations

Future (Phase 2):
    ├─ Bulk create helpers
    ├─ Bulk update helpers
    └─ Transaction wrappers
```

## Integration Layers

```
┌────────────────┐
│  REST API      │  DRF Views
├────────────────┤
│  Services      │  6 service classes
├────────────────┤
│  Models        │  Django ORM
├────────────────┤
│  Database      │  PostgreSQL/SQLite
├────────────────┤
│  Extern APIs   │  Shure/Sennheiser
└────────────────┘
```

---

For more details, see:
- `docs/services-layer.md` - Complete guide
- `docs/services-quick-reference.md` - Quick lookup
- `docs/services-best-practices.md` - Development standards
