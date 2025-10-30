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

### 1. Plugin Architecture (`micboard/plugins/`)
**Purpose**: Extensible system for supporting multiple wireless microphone manufacturers

**Key Components**:
- `ManufacturerPlugin` - Abstract base class defining plugin interface
- `get_manufacturer_plugin()` - Dynamic plugin loading function
- Manufacturer-specific plugins (e.g., `ShurePlugin`, `SennheiserPlugin`)

**Plugin Interface**:
```python
class ManufacturerPlugin(ABC):
    @property
    @abstractmethod
    def manufacturer_code(self) -> str: ...

    @property
    @abstractmethod
    def manufacturer_name(self) -> str: ...

    @abstractmethod
    def get_devices(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def transform_device_data(self, device_data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    def check_health(self) -> Dict[str, Any]: ...
```

**Features**:
- Dynamic plugin discovery and loading
- Manufacturer data isolation
- Standardized API interface across manufacturers
- Easy extensibility for new manufacturers

### 2. Polling Service (`poll_devices.py`)
**Purpose**: Background service that continuously fetches data from multiple manufacturers

**Workflow**:
1. Iterate through configured manufacturers
2. Load appropriate plugin for each manufacturer
3. Poll manufacturer API at regular intervals
4. Transform and validate data using plugin
5. Update Django models with manufacturer relationships
6. Broadcast updates via WebSocket to connected clients
7. Cache data for quick API responses

**Configuration**:
- Per-manufacturer polling intervals
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

API health is aggregated per-manufacturer and surfaced in the public UI as a footer indicator; each plugin exposes a `check_health()` method and the application aggregates these results via a context processor to show overall and per-manufacturer statuses.

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
- Start real-time subscriptions after polling
- Support for async execution with Django-Q

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
1. poll_devices timer triggers
2. For each configured manufacturer:
   a. Load manufacturer plugin
   b. Call plugin.get_devices()
   c. Transform data using plugin.transform_device_data()
   d. Update Django models with manufacturer relationships
3. Cache manufacturer-filtered data
4. Broadcast updates to WebSocket clients
5. Sleep until next interval
```

### Real-time Updates (WebSocket + SSE)
```
1. poll_devices triggers manufacturer polling
2. After polling completes, start real-time subscriptions:
   a. For Shure: Start WebSocket subscriptions
   b. For Sennheiser: Start SSE subscriptions
3. RealTimeConnection models track subscription status
4. Health monitoring tasks check connection health
5. Updates broadcast via WebSocket to connected clients
6. Automatic reconnection on failures
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
Plugins are automatically discovered through the `get_manufacturer_plugin()` function:

```python
def get_manufacturer_plugin(manufacturer: Manufacturer) -> ManufacturerPlugin:
    """Load and return the appropriate plugin for a manufacturer"""
    plugin_class = _PLUGIN_CLASSES.get(manufacturer.code)
    if not plugin_class:
        raise ValueError(f"No plugin found for manufacturer: {manufacturer.code}")
    return plugin_class(manufacturer)
```

### Adding New Manufacturers
1. Create a new plugin class inheriting from `ManufacturerPlugin`
2. Implement required methods and properties
3. Register the plugin in `micboard/plugins/__init__.py`
4. Configure the manufacturer in the database
5. Restart the application

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
        'api_url': 'http://shure-api.example.com',
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
- poll_devices in separate terminal
- In-memory channel layer
- SQLite database
```

### Production
```
Multi-Process:
- Nginx (reverse proxy, static files)
- Daphne (ASGI server for WebSockets)
- poll_devices (systemd service)
- Redis (channel layer, caching)
- PostgreSQL (database)
- Supervisor/systemd (process management)
```

## Scalability Considerations

### Horizontal Scaling
- Multiple Daphne workers for WebSocket connections
- Multiple poll_devices instances (with leader election)
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

## Support and Documentation

- **Shure System API**: https://www.shure.com/en-US/products/software/systemapi
- **Django Channels**: https://channels.readthedocs.io/
- **Original Micboard**: https://github.com/mikecentral/micboard

---

This architecture provides a robust, scalable, and maintainable solution for wireless microphone monitoring using modern Django practices and official Shure APIs.
