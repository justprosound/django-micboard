# Rate Limiting and Retry Logic

## Overview

Micboard implements comprehensive rate limiting and retry logic for both API consumption (as a client to Shure System API) and API serving (protecting micboard endpoints from abuse).

## Client-Side: Shure System API Client

### Automatic Retry with Exponential Backoff

The `ShureSystemAPIClient` uses urllib3's `Retry` class with requests' `HTTPAdapter` to automatically retry failed requests.

**Configuration** (in `settings.py`):
```python
MICBOARD_CONFIG = {
    'SHURE_API_MAX_RETRIES': 3,  # Number of retry attempts
    'SHURE_API_RETRY_BACKOFF': 0.5,  # Base backoff in seconds (exponential)
    'SHURE_API_RETRY_STATUS_CODES': [429, 500, 502, 503, 504],  # Codes to retry
}
```

**How it works**:
- Request fails with status 429 (rate limited) → waits 0.5s, retries
- Second failure → waits 1.0s (0.5 * 2^1), retries
- Third failure → waits 2.0s (0.5 * 2^2), retries
- After 3 retries → returns None, logs error

**Retried status codes**:
- `429 Too Many Requests` - Server rate limit hit
- `500 Internal Server Error` - Temporary server issue
- `502 Bad Gateway` - Proxy/gateway error
- `503 Service Unavailable` - Server overloaded
- `504 Gateway Timeout` - Upstream timeout

### Rate Limiting (Outgoing Requests)

Prevents micboard from overwhelming the Shure System API with too many requests.

**Implementation**:
```python
@rate_limit(calls_per_second=5.0)
def get_devices(self):
    # Maximum 5 calls per second to this method
    pass
```

**Per-method limits**:
- `get_devices()`: 5 requests/second
- `get_device()`: 10 requests/second
- `get_device_channels()`: 10 requests/second
- `get_transmitter_data()`: 10 requests/second
- `discover_devices()`: 2 requests/second (expensive operation)

**How it works** (Token Bucket Algorithm):
1. Each method call checks last call timestamp in Django cache
2. If time since last call < minimum interval → sleeps for the difference
3. Updates cache with current timestamp
4. Proceeds with request

**Example**:
```python
client = ShureSystemAPIClient()

# First call - goes immediately
client.get_devices()

# Second call immediately after - sleeps 0.2s (1/5 = 0.2)
client.get_devices()  

# Third call 0.3s later - goes immediately (>0.2s elapsed)
client.get_devices()
```

## Server-Side: Micboard API Endpoints

### Rate Limiting (Incoming Requests)

Protects micboard from abuse by limiting requests per IP address or authenticated user.

**Endpoints and limits**:

| Endpoint | Limit | Window | Notes |
|----------|-------|--------|-------|
| `/api/data/` | 120 req | 60s | Main data feed (2 req/sec) |
| `/api/discover/` | 5 req | 60s | Discovery is expensive |
| `/api/refresh/` | 10 req | 60s | Force refresh |
| `/api/config/` | 60 req | 60s | Config updates |
| `/api/group/` | 60 req | 60s | Group updates |

**Implementation**:
```python
@rate_limit_view(max_requests=120, window_seconds=60)
def data_json(request):
    # Limited to 120 requests per 60 seconds per IP
    pass
```

**How it works** (Sliding Window Algorithm):
1. Extract IP address from request (or user ID if authenticated)
2. Retrieve request timestamps from cache for this IP/user
3. Filter out timestamps older than window (60s)
4. If count >= max_requests → return HTTP 429
5. Otherwise, add current timestamp and proceed

**Response when rate limited**:
```json
{
    "error": "Rate limit exceeded",
    "detail": "Maximum 120 requests per 60 seconds",
    "retry_after": 45
}
```
- HTTP Status: `429 Too Many Requests`
- Header: `Retry-After: 45` (seconds until rate limit resets)

### Decorators

**`@rate_limit_view`** - For function-based views:
```python
from .decorators import rate_limit_view

@rate_limit_view(max_requests=30, window_seconds=60)
def my_view(request):
    return JsonResponse({'data': 'value'})
```

**`@rate_limit_user`** - Rate limit by authenticated user:
```python
from .decorators import rate_limit_user
from django.contrib.auth.decorators import login_required

@login_required
@rate_limit_user(max_requests=100, window_seconds=60)
def user_specific_view(request):
    return JsonResponse({'data': 'value'})
```

**Custom key function**:
```python
def custom_key(request):
    # Rate limit by API key instead of IP
    return f'rate_limit_{request.GET.get("api_key")}'

@rate_limit_view(max_requests=1000, window_seconds=3600, key_func=custom_key)
def api_view(request):
    return JsonResponse({'data': 'value'})
```

## Configuration

### Django Settings

**Cache backend** (required for rate limiting):
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

**Alternative** (development only):
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

### Micboard Configuration

```python
MICBOARD_CONFIG = {
    # Shure System API
    'SHURE_API_BASE_URL': 'http://localhost:8080',
    'SHURE_API_TIMEOUT': 10,
    
    # Retry configuration
    'SHURE_API_MAX_RETRIES': 3,
    'SHURE_API_RETRY_BACKOFF': 0.5,
    'SHURE_API_RETRY_STATUS_CODES': [429, 500, 502, 503, 504],
    
    # Polling
    'POLL_INTERVAL': 5,
    'CACHE_TIMEOUT': 30,
}
```

## Monitoring

### Logging

Rate limiting events are logged at different levels:

**Client-side**:
```python
# DEBUG level - rate limiting sleep
logger.debug(f"Rate limiting get_devices: sleeping 0.234s")

# ERROR level - all retries exhausted
logger.error(f"API request failed: GET /api/v1/devices - ConnectionError")
```

**Server-side**:
```python
# WARNING level - rate limit exceeded
logger.warning(f"Rate limit exceeded for rate_limit_data_json_192.168.1.100: 121/120 requests in 60s window")
```

### Cache Keys

Rate limit state is stored in cache with these key patterns:

**Client-side** (outgoing):
- `rate_limit_ShureSystemAPIClient_get_devices`
- `rate_limit_ShureSystemAPIClient_discover_devices`

**Server-side** (incoming):
- `rate_limit_data_json_192.168.1.100_window` (IP-based)
- `rate_limit_user_42_window` (user-based)

## Testing Rate Limits

### Test Client-Side Rate Limiting

```python
import time
from micboard.shure_api_client import ShureSystemAPIClient

client = ShureSystemAPIClient()

# This should work fine
for i in range(3):
    start = time.time()
    client.get_devices()
    elapsed = time.time() - start
    print(f"Call {i+1}: {elapsed:.3f}s")

# Output:
# Call 1: 0.145s  (normal request)
# Call 2: 0.345s  (slept 0.2s due to rate limit)
# Call 3: 0.345s  (slept 0.2s due to rate limit)
```

### Test Server-Side Rate Limiting

```bash
# Use curl to test rate limiting
for i in {1..125}; do
    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/data/
done

# First 120 requests: 200
# Next 5 requests: 429
```

### Test Retry Logic

```python
# Temporarily break Shure API server to test retries
# Watch logs for retry attempts:

client = ShureSystemAPIClient()
client.get_devices()  # Will retry 3 times, then return None

# Logs will show:
# WARNING: Retrying (Retry(total=2, ...)) after connection error
# WARNING: Retrying (Retry(total=1, ...)) after connection error
# WARNING: Retrying (Retry(total=0, ...)) after connection error
# ERROR: API request failed: GET /api/v1/devices - ConnectionError
```

## Best Practices

### For API Consumers

1. **Handle None responses** - API methods return None on failure:
   ```python
   devices = client.get_devices()
   if devices is None:
       logger.error("Failed to fetch devices")
       return
   ```

2. **Don't retry manually** - The client handles retries automatically

3. **Use caching** - Cache responses to reduce API calls:
   ```python
   cached = cache.get('devices')
   if cached is None:
       cached = client.get_devices()
       cache.set('devices', cached, timeout=30)
   ```

### For API Providers

1. **Set appropriate limits** - Balance usability and protection:
   - Frequent operations: 60-120 req/min
   - Expensive operations: 5-10 req/min
   - Discovery/search: 2-5 req/min

2. **Return proper headers** - Always include `Retry-After`:
   ```python
   return JsonResponse(
       {'error': 'Rate limit exceeded'},
       status=429,
       headers={'Retry-After': str(retry_after)}
   )
   ```

3. **Use user-based limits** for authenticated endpoints:
   ```python
   @login_required
   @rate_limit_user(max_requests=1000, window_seconds=3600)
   def premium_api(request):
       pass
   ```

## Troubleshooting

### "Rate limit exceeded" errors

**Symptom**: HTTP 429 responses from micboard API

**Solutions**:
1. Check if client is making excessive requests
2. Increase rate limit in decorator if legitimate use case
3. Implement client-side caching
4. Use authenticated endpoints with higher limits

### Slow API responses

**Symptom**: Requests take longer than expected

**Possible cause**: Client-side rate limiting is sleeping

**Solutions**:
1. Check if you're making rapid sequential requests
2. Increase `calls_per_second` in `@rate_limit` decorator
3. Make requests in parallel (different methods can run concurrently)

### Retry exhaustion

**Symptom**: API methods returning None frequently

**Solutions**:
1. Check Shure System API server status
2. Increase `SHURE_API_MAX_RETRIES`
3. Increase `SHURE_API_TIMEOUT`
4. Check network connectivity

### Cache not working

**Symptom**: Rate limits not being enforced or reset too quickly

**Solutions**:
1. Verify Redis is running: `redis-cli ping`
2. Check cache configuration in settings
3. Test cache: `python manage.py shell`
   ```python
   from django.core.cache import cache
   cache.set('test', 'value', 60)
   print(cache.get('test'))  # Should print 'value'
   ```

## Performance Impact

### Memory Usage

- **Per rate-limited endpoint**: ~100 bytes per IP address
- **Per client method**: ~50 bytes total
- **Example**: 100 IPs × 5 endpoints = ~50KB

### CPU Impact

- **Minimal**: ~0.1ms per rate limit check
- **Negligible** compared to actual request processing

### Cache Load

- **Writes per request**: 1-2 cache operations
- **Reads per request**: 1 cache operation
- **Cache TTL**: Automatic cleanup after window expires

## Dependencies

- **Django Cache Framework**: Required for all rate limiting
- **Redis** (recommended): Fast, persistent cache backend
- **urllib3**: Retry logic for HTTP requests
- **requests**: HTTP client with session management
