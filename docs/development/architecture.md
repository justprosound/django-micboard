# Micboard Django App - Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Multi-Manufacturer Device Networks          │
│  (Shure, Sennheiser, Audio-Technica, etc.)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Network Communication
                           │
┌──────────────────────────▼──────────────────────────────────┐
│           Manufacturer API Servers/Middleware               │
│  - Shure System API                                        │
│  - Sennheiser API                                          │
│  - Other manufacturer APIs                                 │
│  - Device discovery and communication                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ HTTP/HTTPS REST APIs
                           │
┌──────────────────────────▼──────────────────────────────────┐
│         Micboard Django App (This Application)               │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  Plugin Architecture                           │         │
│  │  - ManufacturerPlugin abstract base class     │         │
│  │  - Dynamic plugin loading                      │         │
│  │  - Manufacturer-specific implementations       │         │
│  └────────────┬───────────────────────────────────┘         │
│               │                                              │
│  ┌────────────▼───────────────────────────────────┐         │
│  │  poll_devices command                          │         │
│  │  - Multi-manufacturer polling                  │         │
│  │  - Model updates with manufacturer isolation   │         │
│  │  - WebSocket broadcasting                      │         │
│  └────────────┬───────────────────────────────────┘         │
│               │                                              │
│  ┌────────────▼───────────────────────────────────┐         │
│  │  Django Models                                 │         │
│  │  - Manufacturer, Receiver, Transmitter         │         │
│  │  - Group, Config (manufacturer-aware)          │         │
│  │  - Database persistence with data isolation    │         │
│  └────────────┬───────────────────────────────────┘         │
│               │                                              │
│               ├──────────────┬─────────────────┐            │
│               │              │                 │            │
│  ┌────────────▼───────┐ ┌───▼────────┐ ┌──────▼──────┐     │
│  │  Views/API         │ │ WebSocket  │ │ Django      │     │
│  │  - REST endpoints  │ │ Consumers  │ │ Admin       │     │
│  │  - Manufacturer    │ │ - Real-time│ │ - Config UI │     │
│  │    filtering       │ │   updates  │ │             │     │
│  └────────────────────┘ └────────────┘ └─────────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ HTTP/WebSocket
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Web Browser / Client                       │
│  - Dashboard UI                                              │
│  - Real-time updates                                         │
│  - Multi-manufacturer device management                     │
└──────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Plugin Architecture

**Purpose**: Extensible support for manufacturer protocols without duplicating shared transport
and safety behavior.

**Key Components**:
- `micboard.services.common.base.plugin.ManufacturerPlugin` - Plugin contract
- `micboard.services.manufacturer.plugin_registry.PluginRegistry` - Cached construction boundary
- `micboard.services.common.base.client.BaseHTTPClient` - Shared verified HTTP transport
- `micboard.integrations.<vendor>` - Manufacturer-local clients, discovery, transforms, and streams

The contract exposes `name`, `code`, inventory and per-device reads, transformation, health,
discovery-IP management, and a client boundary. Protocol details remain in each integration. See
[Manufacturer plugin development](../plugin-development.md) for the complete live contract and a
copy-safe implementation workflow.

**Features**:
- Convention-based plugin discovery and cached construction
- Shared response bounds, retries, TLS validation, rate limiting, and exception behavior
- Manufacturer data isolation
- Independently testable protocol adapters

### 2. Polling Service (`poll_devices.py`)
**Purpose**: One-shot command and service that fetch data from multiple manufacturers

**Workflow**:
1. Iterate through configured manufacturers
2. Load appropriate plugin for each manufacturer
3. Poll each manufacturer API once per invocation
4. Transform and validate data using plugin
5. Update Django models with manufacturer relationships
6. Broadcast updates via WebSocket to connected clients
7. Cache data for quick API responses

**Configuration**:
- Deployment-controlled polling intervals
- Manufacturer-specific settings
- WebSocket broadcasting enable/disable
- Logging and error handling

### 3. Real-Time Connection Management (`RealTimeConnection` Model)
**Purpose**: Track and monitor real-time connections for automatic failover and health monitoring

**Key Components**:
- `RealTimeConnection` model - Tracks SSE/WebSocket connection lifecycle
- Health monitoring tasks - Automatic cleanup and status reporting
- Management commands - CLI tools for connection monitoring
- Admin interface - Visual oversight of connection health

**Connection States**:
- `connecting` - Establishing connection
- `connected` - Active real-time updates
- `disconnected` - Temporarily offline
- `error` - Connection failed with errors
- `stopped` - Intentionally stopped

**Features**:
- Automatic reconnection with exponential backoff
- Error tracking and recovery
- Connection duration monitoring
- Health status aggregation
- Manufacturer-aware connection management

### 4. WebSocket Consumer (`consumers.py`)
**Purpose**: Real-time bidirectional communication with clients

**Features**:
- Async WebSocket handling
- Channel layer integration for broadcasting
- Client command handling (ping/pong)
- Automatic reconnection support
- Manufacturer-aware message filtering

**Message Types**:
- `device_update` - Full device data updates (manufacturer-filtered)
- `status_update` - Status messages
- `ping/pong` - Connection health checks

### 4. Django Models

#### Manufacturer
- Represents a wireless microphone manufacturer
- Stores manufacturer code, name, and configuration
- Central point for manufacturer-specific settings

#### Receiver
- Represents a wireless receiver (manufacturer-aware)
- Foreign key to Manufacturer model
- Tracks API device ID, IP, type, slot
- Records last seen timestamp

#### Transmitter
- Transmitter/microphone data
- Battery, audio levels, RF metrics
- Frequency, antenna, quality info
- Auto-updated by polling service

#### DiscoveredDevice
- Network-discovered devices before registration
- Manufacturer relationship for proper categorization
- Temporary storage during device discovery

#### RealTimeConnection
- Tracks real-time subscription connections (SSE/WebSocket)
- Connection status, error tracking, and reconnection logic
- One-to-one relationship with Receiver model
- Automatic health monitoring and cleanup

#### Group & MicboardConfig
- Logical grouping of devices
- Key-value configuration storage
- Optional manufacturer relationships for manufacturer-specific settings

### Admin Hardware Layout & Health

The Django admin includes a "Hardware Layout Overview" to provide a compact, hardware-first view of receivers grouped by manufacturer and location. It focuses on the mapping Receiver -> Channel -> Frequency and optionally the assigned user. This view is useful for site technicians to quickly confirm physical configurations.

API health is probed by native Huey tasks and surfaced in the public UI as a footer indicator.
The context processor reads a bounded aggregate from cache, falling back to the latest persisted
per-manufacturer health logs; public request rendering never performs manufacturer network I/O.

### 5. Views and API Endpoints

**Dashboard Views**:
- `/` - Main monitoring dashboard (manufacturer-filtered)
- `/about/` - About page

**API Endpoints** (all support `?manufacturer=code` filtering):
- `GET /api/data/` - Current device data (cached, manufacturer-filtered)
- `POST /api/discover/` - Trigger device discovery (manufacturer-specific)
- `POST /api/refresh/` - Force data refresh (manufacturer-specific)
- `POST /api/config/` - Update global/manufacturer-specific config
- `POST /api/group/` - Manage groups
- `GET /api/receivers/` - List receivers (manufacturer-filtered)
- `GET /api/receivers/{id}/` - Get receiver details
- `GET /api/health/` - Check API health (per-manufacturer)

### 5. Management Commands

**Real-Time Status** (`realtime_status`):
- Display connection status summary
- Filter by manufacturer or status
- Show detailed connection information
- Color-coded output for quick status assessment

**Device Polling** (`poll_devices`):
- Poll manufacturer APIs for device data
- Update models and broadcast via WebSocket
- Evaluate a hard-bounded set of alert-eligible wireless units
- Never start or enqueue real-time subscription supervisors
- Support for async execution with native Huey

### 6. Admin Interface

**Real-Time Connections**:
- Visual monitoring of connection health
- Color-coded status indicators
- Bulk actions for connection management
- Detailed connection history and error tracking

**Hardware Layout Overview**:
- Compact view of receivers grouped by manufacturer and location
- Focus on Receiver -> Channel -> Frequency mapping
- Useful for site technicians to verify physical configurations

### 7. Views and API Endpoints

**Dashboard Views**:
- `/` - Main monitoring dashboard (manufacturer-filtered)
- `/about/` - About page

**API Endpoints** (all support `?manufacturer=code` filtering):
- `GET /api/data/` - Current device data (cached, manufacturer-filtered)
- `POST /api/discover/` - Trigger device discovery (manufacturer-specific)
- `POST /api/refresh/` - Force data refresh (manufacturer-specific)
- `POST /api/config/` - Update global/manufacturer-specific config
- `POST /api/group/` - Manage groups
- `GET /api/receivers/` - List receivers (manufacturer-filtered)
- `GET /api/receivers/{id}/` - Get receiver details
- `GET /api/health/` - Check API health (per-manufacturer)

## Data Flow

### Normal Operation (Polling)
```
1. A deployment scheduler invokes poll_devices --async
2. For each configured manufacturer:
   a. Load manufacturer plugin
   b. Call plugin.get_devices()
   c. Transform data using plugin.transform_device_data()
   d. Update Django models with manufacturer relationships
3. Cache manufacturer-filtered data
4. Broadcast updates to WebSocket clients
5. Exit; the deployment scheduler controls the next interval
```

### Real-time Updates (WebSocket + SSE)
```
1. The host explicitly launches a foreground command or native Huey task entrypoint:
   a. For Shure: start the WebSocket supervisor
   b. For Sennheiser: start the SSE supervisor
2. A process-shared cache lease permits one supervisor per transport/manufacturer
3. Hard device and concurrency limits bound subscription work
4. RealTimeConnection models track subscription status
5. Health monitoring tasks check connection health
6. Updates broadcast via WebSocket to connected clients
7. Polling runs independently and never starts supervisors
```

### API Request Flow
```
1. Client requests /api/data/?manufacturer=shure
2. Check manufacturer-filtered cache
3. If cached: return immediately
4. If not: query models with manufacturer filter
5. Transform to JSON using manufacturer-aware serializers
6. Cache result with manufacturer key
7. Return to client
```

## Plugin System

### Plugin Discovery
`PluginRegistry` discovers plugins from the manufacturer code and caches the selected class:

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

plugin_class = PluginRegistry.get_plugin_class("shure")
plugin = PluginRegistry.get_plugin("shure", manufacturer=manufacturer)
```

For code `acme_audio`, class discovery imports `micboard.integrations.acme_audio.plugin` and
prefers `AcmeAudioPlugin`. No package initializer or registry map needs editing.

### Adding New Manufacturers
1. Create `micboard/integrations/<code>/plugin.py`.
2. Implement a concrete, conventionally named `ManufacturerPlugin` subclass.
3. Keep device, discovery, transform, and streaming behavior in that integration package.
4. Create or enable a `Manufacturer` row whose `code` matches the package name.
5. Verify `PluginRegistry.get_plugin_class("<code>")` resolves the class.

### Data Isolation
- Each manufacturer's data is stored with manufacturer relationships
- API responses are filtered by manufacturer code
- Configuration can be global or manufacturer-specific
- WebSocket broadcasts include manufacturer context

## Configuration Management

### Manufacturer Configuration
Each manufacturer is configured in the database with:

- **code**: Unique identifier (e.g., 'shure', 'sennheiser')
- **name**: Human-readable name
- **config**: JSON configuration object with API credentials and settings

### Settings Integration
All configuration is centralized in Django settings:

```python
MICBOARD_CONFIG = {
    'DEFAULT_POLLING_INTERVAL': 10,
    'WEBSOCKET_BROADCASTING': True,
    'CACHE_TIMEOUT': 30,
}
```

### Manufacturer-Specific Settings
Manufacturer configurations are stored in the database:

```python
# Shure manufacturer configuration
manufacturer = Manufacturer.objects.create(
    code='shure',
    name='Shure Incorporated',
    config={
        'api_url': 'https://shure-api.example.com',
        'api_key': 'your-api-key',
        'timeout': 30,
        'polling_interval': 10,
    }
)
```

### Environment Variables (Recommended for Production)
```bash
export SHURE_API_URL="https://api.shure.com"
export SHURE_API_KEY="secret-key"
export SENNHEISER_API_URL="https://api.sennheiser.com"
export SENNHEISER_API_KEY="another-secret"
```

### Global vs Manufacturer-Specific Config
- **Global Config**: Stored in `MicboardConfig` with `manufacturer=None`
- **Manufacturer Config**: Stored in `MicboardConfig` with `manufacturer` set
- **Plugin Config**: Stored in `Manufacturer.config` JSON field

## Deployment Architecture

### Development
```
Single Machine:
- Django runserver
- poll_devices for one-shot device refreshes
- In-memory channel layer
- SQLite database
```

### Production
```
Multi-Process:
- Nginx (reverse proxy, static files)
- Daphne (ASGI server for WebSockets)
- Native Huey consumer
- Deployment scheduler invoking poll_devices --async
- Redis (channel layer, caching)
- PostgreSQL (database)
- Supervisor/systemd (process management)
```

## Scalability Considerations

### Horizontal Scaling
- Multiple Daphne workers for WebSocket connections
- Huey workers consuming queued polling tasks
- Load balancer for HTTP traffic
- Redis for shared state

### Performance Optimization
- Redis caching for API responses
- Database query optimization (select_related, prefetch_related)
- WebSocket connection pooling
- API request batching

## Security

### Authentication
- Required Shure System API authentication (shared secret)
- Django session-based auth for admin
- WebSocket authentication via Django middleware

### Network Security
- TLS/SSL for Shure API communication
- HTTPS for web traffic
- WSS (WebSocket Secure) for production
- Firewall rules for Shure device network

## Monitoring and Logging

### Logging Components
- API client logs (requests, errors)
- Polling service logs (updates, errors)
- WebSocket logs (connections, disconnections)
- Django request logs

### Metrics to Monitor
- API response times
- Device polling success rate
- WebSocket connection count
- Database query performance
- Cache hit rates

## Error Handling

### API Failures
- Automatic retry with backoff
- Graceful degradation (use cached data)
- Error logging and alerting
- Status indicator in UI

### Database Errors
- Transaction rollback
- Integrity constraint handling
- Connection pool management

### WebSocket Errors
- Automatic reconnection
- Message queuing during disconnection
- Connection health monitoring

## Future Enhancements

### Recently Implemented
- **Real-Time Subscriptions** - SSE/WebSocket connections with automatic failover
- **Connection Health Monitoring** - RealTimeConnection model and health tasks
- **Management Commands** - CLI tools for monitoring and status checking
- **Admin Interface** - Visual oversight of real-time connection health

### Planned Features
- **Additional Manufacturer Plugins** - Audio-Technica, Lectrosonics
- **Historical Data Storage** - Time-series data for trending and analytics
- **Advanced Alert System** - Battery/RF issues with manufacturer-specific thresholds
- **Mobile App Support** - Native apps for iOS/Android
- **Multi-Site Deployment** - Centralized monitoring across multiple locations
- **Advanced Reporting** - Manufacturer-specific analytics and reports

### Integration Opportunities
- **Notification Systems** - Slack/Teams integrations with manufacturer context
- **Monitoring Dashboards** - Grafana/Prometheus with manufacturer filtering
- **Syslog Integration** - Centralized logging with manufacturer tags
- **Calendar Integration** - Event-based monitoring schedules
- **Asset Management** - Integration with IT asset management systems

## Migration from Original Micboard

### Advantages of New Architecture
1. **Official API**: Uses Shure's supported API instead of reverse-engineered protocols
2. **Maintainability**: Cleaner separation of concerns
3. **Scalability**: Easier to scale horizontally
4. **Real-time**: Better WebSocket implementation
5. **Database**: Persistent storage of device configurations
6. **Modern**: Uses current Django best practices

### Migration Path
1. Install Shure System API server
2. Run both systems in parallel
3. Verify data accuracy
4. Switch DNS/routing to new system
5. Decommission old system

## Troubleshooting Guide

### Common Issues

**Issue**: No devices detected
- **Solution**: Check Shure System API connectivity, verify devices are on network

**Issue**: WebSocket disconnects frequently
- **Solution**: Check Redis connection, increase timeout values, verify network stability

**Issue**: Slow API responses
- **Solution**: Check Redis cache, optimize database queries, increase polling interval

**Issue**: High CPU usage
- **Solution**: Increase polling interval, reduce log verbosity, optimize queries

## Manufacturer Integration Guides

Comprehensive integration documentation for supported manufacturers:

### Shure System API
- **Guide:** [Shure Integration Guide](../shure-integration.md)
- **Contents:** Authentication, API endpoints, configuration, troubleshooting
- **API Reference:** https://www.shure.com/en-US/products/software/systemapi
- **Status:** Production ready with comprehensive test suite

### Sennheiser SSCv2 API
- **Guide:** [Sennheiser Integration Reference](../integration/integration-references.md#sennheiser-sound-control-protocol)
- **Contents:** Device configuration, authentication, API operations, security
- **API Reference:** https://docs.cloud.sennheiser.com/en-us/api-docs/
- **Status:** Integration ready

## Support and Documentation

### Official API Documentation
- **Shure System API**: https://www.shure.com/en-US/products/software/systemapi
- **Sennheiser Sound Control Protocol**: https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html

### Framework Documentation
- **Django Channels**: https://channels.readthedocs.io/
- **Django REST Framework**: https://www.django-rest-framework.org/

### Micboard Documentation
- **Development Guide**: [development.md](../development.md)
- **Plugin Development**: [Adding New Manufacturers](#adding-new-manufacturers)
- **Rate Limiting**: [Shared Rate Limiter](../integration/integration-references.md#shared-rate-limiter)
- **Integration References**: [integration-references.md](../integration/integration-references.md)
- **Original Micboard**: https://github.com/mikecentral/micboard

---

This architecture provides a robust, scalable, and maintainable solution for wireless microphone monitoring using modern Django practices and manufacturer APIs from Shure, Sennheiser, and other wireless audio providers.
