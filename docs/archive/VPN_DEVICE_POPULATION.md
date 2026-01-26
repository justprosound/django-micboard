# VPN Device Population Guide

This guide covers how to connect Django Micboard to live Shure devices on your VPN network.

## Overview

When you have VPN access to Shure devices (e.g., on your corporate network), you can populate the local development environment with real device data:

```
┌─────────────────────────┐
│ Live Shure Devices      │ (172.21.x.x on VPN)
│ - Transmitters          │
│ - Receivers             │
└──────────┬──────────────┘
           │ (probed)
           ↓
┌─────────────────────────┐
│ device_discovery.py     │ (scripts/)
│ - Scans IP addresses    │
│ - Validates connectivity│
└──────────┬──────────────┘
           │ (saves)
           ↓
┌─────────────────────────┐
│ device_manifest.json    │ (local only, not committed)
│ - Device inventory      │
└──────────┬──────────────┘
           │ (populates)
           ↓
┌─────────────────────────┐
│ Local Django Micboard   │
│ - Polls devices via API │
│ - Real-time monitoring  │
└─────────────────────────┘
```

## Prerequisites

1. **VPN Access**: Connection to network with Shure devices
2. **Device Addresses**: List of IP addresses for your Shure devices
3. **Local Environment**: Django Micboard setup complete (see [CONFIGURATION.md](CONFIGURATION.md))
4. **Local Shure API**: Docker container running (optional but recommended for testing)

## Quick Start

### 1. Set Device IPs

Edit `.env.local` with your device addresses:

```bash
# .env.local
SHURE_DEVICE_IPS=172.21.1.100,172.21.1.101,172.21.1.102,172.21.1.103
```

Or set as environment variable:

```bash
export SHURE_DEVICE_IPS="172.21.1.100,172.21.1.101,172.21.1.102"
```

### 2. Verify VPN Connectivity

Test connectivity to one device:

```bash
python scripts/device_discovery.py test --ip 172.21.1.100
```

Expected output if device is reachable:
```
✓ Device found at 172.21.1.100
{
  "ip": "172.21.1.100",
  "endpoint": "http://172.21.1.100/api/v1/devices",
  "accessible": false,
  "needs_auth": true
}
```

### 3. Discover Devices

Run discovery to probe all devices:

```bash
python scripts/device_discovery.py discover --env
```

This will:
- Probe each IP address in `SHURE_DEVICE_IPS`
- Test both HTTP and HTTPS endpoints
- Create `device_manifest.json` with results
- Report which devices are accessible

Example output:
```
Probing 4 IP addresses...
✓ Device found at 172.21.1.100
✓ Device found at 172.21.1.101
✓ Device found at 172.21.1.102
✓ Device found at 172.21.1.103

✓ Discovered 4 devices
✓ Device manifest saved to device_manifest.json
  ⚠️  WARNING: Do not commit this file!
     It should be in .gitignore
```

### 4. Populate Local API (When Implemented)

Once device population endpoints are implemented:

```bash
python scripts/device_discovery.py populate
```

This will:
- Read `device_manifest.json`
- Connect to local Django API
- Create device records in Django database
- Make devices available in admin interface

## Usage Reference

### Discover from File

If you have device IPs in a file (one per line):

```bash
# devices.txt
172.21.1.100
172.21.1.101
172.21.1.102

python scripts/device_discovery.py discover --file devices.txt
```

### Discover from Comma-Separated List

```bash
python scripts/device_discovery.py discover --ips "172.21.1.100,172.21.1.101,172.21.1.102"
```

### Test Single Device

Debug connectivity to a specific device:

```bash
python scripts/device_discovery.py test --ip 172.21.1.100
```

Response indicates whether device is reachable and what endpoints are available.

### Custom Output File

Save manifest to a different location:

```bash
python scripts/device_discovery.py discover --env --save devices_backup.json
```

## Understanding the Manifest

`device_manifest.json` contains discovered devices:

```json
{
  "devices": [
    {
      "ip": "172.21.1.100",
      "endpoint": "http://172.21.1.100/api/v1/devices",
      "accessible": false,
      "needs_auth": true
    },
    {
      "ip": "172.21.1.101",
      "endpoint": "http://172.21.1.101/api/v1/devices",
      "accessible": true,
      "needs_auth": false
    }
  ],
  "timestamp": "2025-01-15T10:30:45.123456",
  "total_count": 2
}
```

Fields:
- `ip` - Device IP address
- `endpoint` - Discovered API endpoint
- `accessible` - Whether device returned data without authentication
- `needs_auth` - Whether authentication is required (expected for secured devices)

## Viewing Results in Django Admin

After population is complete, view discovered devices in Django admin:

```
http://localhost:8000/admin/micboard/manufacturer/
```

Each device will have:
- Device name/ID
- Device type (transmitter, receiver, etc.)
- Status (online/offline)
- Last polling timestamp

## Troubleshooting

### No Devices Found

**Symptom**: Script reports 0 devices discovered

**Diagnosis**:

1. Check VPN connection:
   ```bash
   ping 172.21.1.100  # Use actual IP
   ```

2. Verify environment variable:
   ```bash
   echo $SHURE_DEVICE_IPS
   ```

3. Test individual device:
   ```bash
   python scripts/device_discovery.py test --ip 172.21.1.100
   ```

4. Check network firewall:
   ```bash
   # From device to local machine
   telnet 172.21.1.100 80  # HTTP
   telnet 172.21.1.100 443 # HTTPS
   ```

### Device Authentication Failed

**Symptom**: `needs_auth: true` but API returns 401/403

**Cause**: Device requires authentication header (Shure shared key)

**Solution**:
- This is expected behavior for secured devices
- Real device data access requires proper authentication
- For testing, use mock data or configure device credentials

### Timeout Errors

**Symptom**: "Connection timed out" when probing devices

**Cause**: Device unreachable on network

**Solution**:
1. Verify VPN connection is active
2. Check device is powered on
3. Confirm network firewall allows traffic
4. Increase timeout in `.env.local`:
   ```bash
   SHURE_DEVICE_DISCOVERY_TIMEOUT=15
   ```

### SSL Certificate Errors

**Symptom**: "SSL: CERTIFICATE_VERIFY_FAILED"

**Solution**: In `.env.local`, disable SSL verification for discovery:
```bash
SHURE_DEVICE_VERIFY_SSL=false
```

⚠️ **Warning**: Only do this for development/testing on trusted networks!

## Security Considerations

### Sensitive Files

These files are created during device population and NOT committed:

- `device_manifest.json` - Contains device IPs and endpoints
- `.env.local` - Contains your actual device IP list
- Any local configuration scripts

All are listed in `.gitignore` for protection.

### Network Security

- VPN connection must be established before running discovery
- Device IPs should be documented internally, not in public repositories
- SSL verification is disabled by default for development (not production)

### Authentication

Currently, the script validates connectivity but does not store authentication credentials. When implementing actual device data retrieval:

1. Use environment variables for credentials
2. Never hardcode API keys or shared keys
3. Store credentials in secure vaults (AWS Secrets Manager, HashiCorp Vault, etc.)
4. Rotate credentials regularly

## Integration with CI/CD

For automated testing with VPN devices:

1. **Store device IPs in CI/CD secrets**:
   ```yaml
   # .github/workflows/integration-test.yml
   env:
     SHURE_DEVICE_IPS: ${{ secrets.SHURE_DEVICE_IPS }}
   ```

2. **Run discovery in pipeline**:
   ```yaml
   - name: Discover devices
     run: python scripts/device_discovery.py discover --env
   ```

3. **Populate test environment**:
   ```yaml
   - name: Populate local API
     run: python scripts/device_discovery.py populate
   ```

4. **Run integration tests**:
   ```yaml
   - name: Run integration tests
     run: pytest tests/integration/ --with-devices
   ```

## Next Steps

1. ✅ Configure device IPs in `.env.local`
2. ✅ Run discovery to validate connectivity
3. 🔄 **Implement device population API endpoints** (next phase)
4. 🔄 **Create device import view in Django admin**
5. 🔄 **Add device polling integration**
6. 🔄 **Test real-time WebSocket updates with live devices**

## Reference

- [Configuration Guide](CONFIGURATION.md) - Environment setup
- [Architecture Documentation](../docs/architecture.md) - System design
- [Shure API Documentation](https://developer.shure.com/docs/systems/wireless/api)
- [Django Admin Documentation](https://docs.djangoproject.com/en/5.0/ref/contrib/admin/)

## Support

For issues with device discovery:

1. Check device is powered on and connected to network
2. Verify VPN connection is active
3. Review [troubleshooting section](#troubleshooting) above
4. Check `device_manifest.json` for discovered devices
5. Review [logs/console output](../docs/development.md#logging) for errors

---

**Remember**: Device IPs and network information should be kept private and not committed to the repository.
