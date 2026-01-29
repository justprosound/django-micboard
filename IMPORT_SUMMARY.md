# Shure Device Import Summary

## Import Results

**Total Devices Discovered:** 212
**Successfully Imported:** 208
**Database:** SQLite (db.sqlite3)

## Device Breakdown by Model

| Model | Count | Description |
|-------|-------|-------------|
| ULXD4Q | 93 | Quad-channel wireless receiver |
| ULXD4D | 84 | Dual-channel wireless receiver |
| SBC220 | 23 | Portable charging station |
| ULXD4 | 7 | Single-channel wireless receiver |
| MXA710-2FT | 1 | Ceiling array microphone |

## Sample Devices

```
Model        Serial          IP               Manufacturer  Name
--------------------------------------------------------------------------------
SBC220       TU221140373     172.21.11.3      Shure
ULXD4D       4172916129      172.21.51.90     Shure
ULXD4Q       4182641539      172.21.6.240     Shure
ULXD4Q       4182774203      172.21.9.139     Shure
ULXD4Q       4182774188      172.21.9.198     Shure
ULXD4Q       4182774107      172.21.9.224     Shure
ULXD4Q       4182774192      172.21.6.205     Shure
ULXD4Q       4182774077      172.21.6.23      Shure
ULXD4Q       4182774603      172.21.11.157    Shure
SBC220       TU182920630     172.21.0.99      Shure
```

## Network Distribution

Devices are distributed across multiple 172.21.x.x subnets:
- 25 different /24 subnets
- 797 discovery IPs configured
- All devices accessible via Shure System API at https://localhost:10000

## Multi-Location Configuration

The system now supports multiple Shure API servers for different locations. Configuration example in `example_project/settings.py`:

```python
MANUFACTURER_API_SERVERS = {
    'shure_hq': {
        'manufacturer': 'shure',
        'base_url': 'https://localhost:10000',
        'shared_key': os.environ.get('MICBOARD_SHURE_API_SHARED_KEY'),
        'verify_ssl': False,
        'location_id': None,  # Optional FK to Location model
        'enabled': True,
    },
    # Additional locations can be added here:
    # 'shure_venue2': {
    #     'manufacturer': 'shure',
    #     'base_url': 'https://venue2.example.com:10000',
    #     'shared_key': 'different_key',
    #     'verify_ssl': True,
    #     'location_id': 2,
    #     'enabled': True,
    # },
}
```

## Import Command Usage

### Import All Devices
```bash
source .env.local
python manage.py import_shure_devices --full
```

### Import from Specific Server
```bash
source .env.local
python manage.py import_shure_devices --server-id shure_hq --full
```

### Dry Run (Preview)
```bash
source .env.local
python manage.py import_shure_devices --dry-run --full
```

## Database Schema Updates

Two migrations were applied:
1. `0001_initial` - Initial schema for all micboard models
2. `0002_alter_wirelesschassis_mac_address` - Made mac_address nullable (not all devices provide MAC addresses via API)

## Next Steps

To add additional Shure API servers:

1. **Update settings.py** - Add new server configuration to `MANUFACTURER_API_SERVERS`
2. **Create Location (optional)** - If you want to associate devices with a physical location:
   ```python
   from micboard.models import Location
   location = Location.objects.create(name="Venue 2", slug="venue2")
   ```
3. **Update server config** - Set `location_id` to the location's ID
4. **Run import** - `python manage.py import_shure_devices --server-id <server_key>`

## API Integration

- **Health Endpoint:** https://localhost:10000/api/v1/devices
- **Authentication:** x-api-key header with shared secret
- **Discovery:** Automatic subnet scanning across configured ranges
- **Polling:** Real-time device state updates via API calls
- **WebSocket:** Live telemetry and event streaming (when configured)
