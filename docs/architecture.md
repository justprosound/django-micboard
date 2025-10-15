# Micboard Django App - Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Shure Devices Network                    │
│  (ULX-D, QLX-D, UHF-R, Axient Digital, etc.)               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Network Communication
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Shure System API Server                         │
│  - Official Shure middleware                                 │
│  - Handles device discovery                                  │
│  - Provides REST API endpoints                               │
│  - Manages device communication                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ HTTP/HTTPS REST API
                           │
┌──────────────────────────▼──────────────────────────────────┐
│         Micboard Django App (This Application)               │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  shure_api_client.py                           │         │
│  │  - API request handling                        │         │
│  │  - Data transformation                         │         │
│  │  - Error handling                              │         │
│  └────────────┬───────────────────────────────────┘         │
│               │                                              │
│  ┌────────────▼───────────────────────────────────┐         │
│  │  poll_devices command                          │         │
│  │  - Background polling                          │         │
│  │  - Model updates                               │         │
│  │  - WebSocket broadcasting                      │         │
│  └────────────┬───────────────────────────────────┘         │
│               │                                              │
│  ┌────────────▼───────────────────────────────────┐         │
│  │  Django Models                                 │         │
│  │  - Device, Transmitter                         │         │
│  │  - Group, Config                               │         │
│  │  - Database persistence                        │         │
│  └────────────┬───────────────────────────────────┘         │
│               │                                              │
│               ├──────────────┬─────────────────┐            │
│               │              │                 │            │
│  ┌────────────▼───────┐ ┌───▼────────┐ ┌──────▼──────┐     │
│  │  Views/API         │ │ WebSocket  │ │ Django      │     │
│  │  - REST endpoints  │ │ Consumers  │ │ Admin       │     │
│  │  - Templates       │ │ - Real-time│ │ - Config UI │     │
│  └────────────────────┘ └────────────┘ └─────────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ HTTP/WebSocket
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Web Browser / Client                       │
│  - Dashboard UI                                              │
│  - Real-time updates                                         │
│  - Device management                                         │
└──────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Shure System API Client (`shure_api_client.py`)
**Purpose**: Abstraction layer for Shure System API communication

**Key Methods**:
- `get_devices()` - Fetch all devices
- `get_device(device_id)` - Get specific device details
- `get_device_channels(device_id)` - Get channel/transmitter data
- `poll_all_devices()` - Full data poll with transformation
- `discover_devices()` - Network device discovery

**Features**:
- Automatic data transformation from Shure API format to micboard format
- Built-in error handling and retry logic
- Session management with authentication
- Configurable timeouts and SSL verification

### 2. Polling Service (`poll_devices.py`)
**Purpose**: Background service that continuously fetches data

**Workflow**:
1. Poll Shure System API at regular intervals
2. Transform and validate data
3. Update Django models (Device, Transmitter)
4. Broadcast updates via WebSocket to connected clients
5. Cache data for quick API responses

**Configuration**:
- Polling interval (default: 10 seconds)
- WebSocket broadcasting enable/disable
- Logging and error handling

### 3. WebSocket Consumer (`consumers.py`)
**Purpose**: Real-time bidirectional communication with clients

**Features**:
- Async WebSocket handling
- Channel layer integration for broadcasting
- Client command handling (ping/pong)
- Automatic reconnection support

**Message Types**:
- `device_update` - Full device data updates
- `status_update` - Status messages
- `ping/pong` - Connection health checks

### 4. Django Models

#### Device
- Represents a Shure receiver
- Tracks API device ID, IP, type, slot
- Records last seen timestamp
- One-to-one with Transmitter

#### Transmitter
- Transmitter/microphone data
- Battery, audio levels, RF metrics
- Frequency, antenna, quality info
- Auto-updated by polling service

#### Group
- Logical grouping of devices
- Custom slot arrangements
- Chart visibility settings

#### MicboardConfig
- Key-value configuration storage
- UI customization
- Feature flags

### 5. Views and API Endpoints

**Dashboard Views**:
- `/` - Main monitoring dashboard
- `/about/` - About page

**API Endpoints**:
- `GET /api/data/` - Current device data (cached)
- `POST /api/discover/` - Trigger device discovery
- `POST /api/refresh/` - Force data refresh
- `POST /api/slot/` - Update slot configuration
- `POST /api/config/` - Update global config
- `POST /api/group/` - Manage groups

## Data Flow

### Normal Operation (Polling)
```
1. poll_devices timer triggers
2. ShureSystemAPIClient.poll_all_devices()
3. For each device:
   a. Fetch device info
   b. Fetch channel data
   c. Transform to micboard format
4. Update Django models
5. Cache data
6. Broadcast to WebSocket clients
7. Sleep until next interval
```

### Real-time Updates (WebSocket)
```
1. Client connects to WebSocket
2. Client joins 'micboard_updates' group
3. When data updates:
   a. poll_devices broadcasts to group
   b. Consumer receives message
   c. Consumer forwards to client
4. Client updates UI
```

### API Request Flow
```
1. Client requests /api/data/
2. Check cache
3. If cached: return immediately
4. If not: query models
5. Transform to JSON
6. Cache result
7. Return to client
```

## Configuration Management

### Settings Integration
All configuration is centralized in Django settings:

```python
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': 'http://localhost:8080',
    'SHURE_API_USERNAME': None,
    'SHURE_API_PASSWORD': None,
    'SHURE_API_TIMEOUT': 10,
    'SHURE_API_VERIFY_SSL': True,
}
```

### Environment Variables (Recommended for Production)
```bash
export SHURE_API_BASE_URL="https://api.example.com"
export SHURE_API_USERNAME="admin"
export SHURE_API_PASSWORD="secret"
```

Then in settings:
```python
import os
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': os.getenv('SHURE_API_BASE_URL'),
    'SHURE_API_USERNAME': os.getenv('SHURE_API_USERNAME'),
    'SHURE_API_PASSWORD': os.getenv('SHURE_API_PASSWORD'),
}
```

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
- Optional Shure System API authentication
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

### Planned Features
- Historical data storage and graphing
- Alert system for battery/RF issues
- Mobile app support
- Multi-site deployment
- Advanced reporting

### Integration Opportunities
- Slack/Teams notifications
- Grafana dashboards
- Prometheus metrics
- Syslog integration
- Calendar integration for events

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
