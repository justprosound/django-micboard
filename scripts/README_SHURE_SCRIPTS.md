# Shure System API Scripts

Collection of reusable Python scripts for managing and testing the Shure System API integration with django-micboard.

## Quick Start

### 1. Health Check (Always Start Here)

```bash
python scripts/shure_api_health_check.py
```

This verifies:
- API connectivity
- Device discovery status
- IP configuration
- Client health

**If this shows 0 devices:** See [Network GUID Troubleshooting](../docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md)

### 2. Configure Discovery IPs

```bash
# Add IPs from file
python scripts/shure_configure_discovery_ips.py --file campus_ips.txt

# Add specific IPs
python scripts/shure_configure_discovery_ips.py --ips 172.21.0.1 172.21.1.1

# List current IPs
python scripts/shure_configure_discovery_ips.py --list

# Clear and reload
python scripts/shure_configure_discovery_ips.py --clear --file ips.txt
```

### 3. Monitor Device Discovery

```bash
python scripts/shure_discovery_monitor.py
```

Watch in real-time as devices are discovered. See alerts when:
- 🆕 New devices appear
- 🔄 Devices change state
- 📊 Periodic summary of discovery progress

### 4. Test Django-Micboard Integration

```bash
python scripts/test_micboard_shure_integration.py
```

Verify that django-micboard can:
- Connect to Shure API
- Fetch devices
- Transform data
- Serialize for WebSocket
- Ready for polling

---

## Environment Setup

All scripts require these environment variables:

```bash
export MICBOARD_SHURE_API_BASE_URL="https://localhost:10000"
export MICBOARD_SHURE_API_SHARED_KEY="<your-shared-key>"
export MICBOARD_SHURE_API_VERIFY_SSL="false"
```

Or create `.env.local` in the project root:

```env
MICBOARD_SHURE_API_BASE_URL=https://localhost:10000
MICBOARD_SHURE_API_SHARED_KEY=<your-shared-key>
MICBOARD_SHURE_API_VERIFY_SSL=false
```

**Never commit `.env.local` to git!**

---

## Script Reference

### `shure_api_health_check.py`

Comprehensive health check and diagnostics.

```bash
# Quick health check
python scripts/shure_api_health_check.py

# Full diagnostics
python scripts/shure_api_health_check.py --full
```

**Checks:**
- API connectivity
- Device discovery status
- Discovery IP configuration
- API endpoints availability
- Client configuration

**Output:**
- ✓ Green = OK
- ⚠ Yellow = Warning (check details)
- ✗ Red = Error (needs attention)

---

### `shure_configure_discovery_ips.py`

Manage discovery IP addresses.

```bash
# List current IPs
python scripts/shure_configure_discovery_ips.py --list

# Add from file
python scripts/shure_configure_discovery_ips.py --file ips.txt

# Add specific IPs
python scripts/shure_configure_discovery_ips.py --ips 172.21.0.1 172.21.1.1 172.21.2.1

# Clear all IPs
python scripts/shure_configure_discovery_ips.py --clear

# Clear and reload
python scripts/shure_configure_discovery_ips.py --clear --file ips.txt

# Validate IPs before adding
python scripts/shure_configure_discovery_ips.py --file ips.txt --validate

# Print summary
python scripts/shure_configure_discovery_ips.py --summary
```

**Batch Processing:**
- Automatically deduplicates IPs
- Adds in batches (default: 100 per request)
- Customize batch size: `--batch-size 50`

**File Format:**
IPs can be space-separated, newline-separated, or mixed:

```
# campus_ips.txt
172.21.0.1 172.21.0.2 172.21.0.3
172.21.1.1
172.21.1.2 172.21.1.3
```

---

### `shure_discovery_monitor.py`

Real-time device discovery monitoring.

```bash
# Monitor with default settings (5s check, 60s summary)
python scripts/shure_discovery_monitor.py

# Faster checks (2s interval)
python scripts/shure_discovery_monitor.py --check-interval 2

# Longer summaries (every 2 minutes)
python scripts/shure_discovery_monitor.py --summary-interval 120

# Run for specific duration (300 seconds)
python scripts/shure_discovery_monitor.py --duration 300
```

**Output:**
- 🆕 NEW DEVICE(S) DISCOVERED - Shows when devices appear
- 🔄 STATE CHANGE - Shows device state transitions
- 📊 SUMMARY - Periodic status with device counts

**Typical Discovery Timeline:**
- 0-10s: Waiting for first responses
- 10-60s: Main discovery period
- 60+s: Continued scanning, fewer new devices

---

### `test_micboard_shure_integration.py`

Validate django-micboard Shure integration.

```bash
# Test all devices
python scripts/test_micboard_shure_integration.py

# Test with sample (first 5 devices)
python scripts/test_micboard_shure_integration.py --sample-size 5
```

**Tests:**
1. Client Initialization
2. Device Fetching
3. Device Data Structure
4. Device Transformation
5. WebSocket URL Generation
6. Data Serialization
7. Polling Readiness

**Success means:**
- Ready to run `manage.py poll_devices`
- Ready for WebSocket subscriptions
- Ready for real-time monitoring

---

## Common Workflows

### Setup Workflow

```bash
# 1. Check API is running and accessible
python scripts/shure_api_health_check.py

# 2. Configure discovery IPs
python scripts/shure_configure_discovery_ips.py --file campus_ips.txt

# 3. Monitor discovery in progress
python scripts/shure_discovery_monitor.py
# Wait for devices to appear...

# 4. Verify django-micboard integration
python scripts/test_micboard_shure_integration.py

# 5. Start polling
python manage.py poll_devices
```

### Debugging Workflow

```bash
# 1. Check API health
python scripts/shure_api_health_check.py

# If connectivity is failing:
# - Verify API is running: net start "Shure System API Service - Standalone"
# - Check firewall allows port 10000
# - Verify shared key is correct

# If 0 devices:
# - See: docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md
# - This is usually wrong NetworkInterfaceId GUID

# 2. Verify IPs are configured
python scripts/shure_configure_discovery_ips.py --list

# 3. Monitor discovery
python scripts/shure_discovery_monitor.py --check-interval 2

# 4. Test integration
python scripts/test_micboard_shure_integration.py
```

### Reconfigure IPs Workflow

```bash
# 1. Clear existing IPs
python scripts/shure_configure_discovery_ips.py --clear

# 2. Add new IPs
python scripts/shure_configure_discovery_ips.py --file new_ips.txt

# 3. Verify
python scripts/shure_configure_discovery_ips.py --summary

# 4. Monitor discovery
python scripts/shure_discovery_monitor.py
```

---

## Troubleshooting

### "Connection refused" Error

```
Error: HTTPSConnectionPool... Connection refused
```

**Solutions:**
1. Check API service is running:
   ```powershell
   Get-Service -Name "*Shure*" | Select-Object Status
   ```

2. Check port 10000 is accessible:
   ```powershell
   Test-NetConnection localhost -Port 10000
   ```

3. Check firewall allows port 10000 (Windows):
   ```powershell
   Get-NetFirewallRule -DisplayName "*Shure*" | Get-NetFirewallPortFilter
   ```

### "Authentication failed" Error

```
Error: SHURE_API_SHARED_KEY is required
```

**Solutions:**
1. Set environment variable:
   ```bash
   export MICBOARD_SHURE_API_SHARED_KEY="<key-from-config>"
   ```

2. Or create `.env.local`:
   ```env
   MICBOARD_SHURE_API_SHARED_KEY=<key>
   ```

3. Get key from Shure API config:
   ```
   C:\ProgramData\Shure\SystemAPI\Standalone\Security\sharedkey.txt
   ```

### "0 devices discovered" After Adding IPs

**This is the most common issue.** See [Network GUID Troubleshooting](../docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md)

**Quick diagnosis:**
```bash
# Check if IPs are configured
python scripts/shure_configure_discovery_ips.py --list

# Monitor for discoveries
python scripts/shure_discovery_monitor.py --duration 120

# Check System API config
# File: C:\ProgramData\Shure\SystemAPI\Standalone\appsettings.Standalone.json5
# Look for NetworkInterfaceId GUID
```

If 0 devices appear after 2+ minutes:
1. Check NetworkInterfaceId GUID is correct
2. Verify network interface has route to device network (172.21.x.x)
3. Check firewall allows UDP 8427 (SLP)

---

## Advanced Usage

### IP File Format Examples

**Comma-separated:**
```
172.21.0.1,172.21.0.2,172.21.0.3
172.21.1.1,172.21.1.2
```

**Space-separated:**
```
172.21.0.1 172.21.0.2 172.21.0.3 172.21.1.1
```

**One per line:**
```
172.21.0.1
172.21.0.2
172.21.0.3
```

**Mixed formats (all supported):**
```
172.21.0.1 172.21.0.2
172.21.0.3,172.21.0.4
172.21.0.5
```

### Generating IP Lists

**Generate 172.21.x.x subnets (255 total):**
```bash
# Linux/Mac
for i in $(seq 0 255); do echo "172.21.$i.1"; done > ips.txt

# Windows PowerShell
0..255 | ForEach-Object { "172.21.$_.1" } | Out-File ips.txt

# Add via script
python scripts/shure_configure_discovery_ips.py --file ips.txt
```

### Batch Operations

**Large IP counts:**
```bash
# Use smaller batches for very large lists
python scripts/shure_configure_discovery_ips.py --file ips.txt --batch-size 50

# With validation
python scripts/shure_configure_discovery_ips.py --file ips.txt --batch-size 50 --validate
```

---

## Integration with Django Management Commands

Once devices are discovered, start the polling command:

```bash
# Start device polling
python manage.py poll_devices

# In another terminal, monitor discovery
python scripts/shure_discovery_monitor.py
```

---

## Related Documentation

- [GUID Troubleshooting](../docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md) - Critical for 0 device issues
- [API Reference](../docs/api/endpoints.md) - Shure API endpoints used
- [Configuration](../docs/configuration.md) - Django settings
- [WebSocket](../docs/api/websocket.md) - Real-time updates

---

## Quick Reference

| Task | Command |
|------|---------|
| Health check | `python scripts/shure_api_health_check.py` |
| List IPs | `python scripts/shure_configure_discovery_ips.py --list` |
| Add IPs | `python scripts/shure_configure_discovery_ips.py --file ips.txt` |
| Monitor discovery | `python scripts/shure_discovery_monitor.py` |
| Test integration | `python scripts/test_micboard_shure_integration.py` |

---

**Last Updated:** January 21, 2026  
**Status:** Production Ready
