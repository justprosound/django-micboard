# Phase 3: Testing & Integration - Quick Start

## 🎯 Objective
Test django-micboard models and services with real data from the working Shure System API.

## ✅ Prerequisites Met
- ✅ 30+ devices discovered and ONLINE
- ✅ Shure System API fully functional
- ✅ Scripts refactored and secured
- ✅ Documentation organized

---

## 🚀 Start Here: Run Tests in Order

### Test 1: Model Population (15 minutes)
```bash
# Test creating Device models from real Shure data
python scripts/test_models_with_shure_data.py --sample-size 5
```

**What this tests:**
- ✓ Device model creation from API data
- ✓ Transmitter/Receiver relationships
- ✓ Firmware/serial property storage
- ✓ State tracking and updates
- ✓ Telemetry data storage
- ✓ Query and filtering

**Expected output:**
```
✓ Fetched 30 devices from API
✓ Created test location: API Test Location
✓ Populated 5 devices
  ✓ Created: ULXD4D @ 172.21.2.140 (Serial: 4192900300)
  ...
✓ Total devices: 5
✓ Online devices: 5
✓ All tests passed
```

**If this fails:**
- Check database is initialized: `python manage.py migrate`
- Check Shure API is running: `python scripts/shure_api_health_check.py`
- Check credentials in Django settings

---

### Test 2: Verify Polling Command (10 minutes)
```bash
# Dry-run: see what polling will do
python manage.py poll_devices --dry-run

# Or run for 30 seconds
python manage.py poll_devices --duration 30
```

**What this does:**
- Fetches devices from Shure API
- Creates/updates Device models
- Broadcasts updates via WebSocket
- Stores telemetry

**Expected output:**
```
Polling devices...
Found 30 devices
Updating Device model for: ULXD4D @ 172.21.2.140
Broadcasting update: Device ULXD4D is ONLINE
...
```

**If this fails:**
- Verify models test passed first
- Check `python manage.py help poll_devices`
- Monitor: `python scripts/shure_discovery_monitor.py` in another terminal

---

### Test 3: Test API Endpoints (10 minutes)
```bash
# Start Django server
python manage.py runserver

# In another terminal, test endpoints
curl http://localhost:8000/api/v1/devices/
curl http://localhost:8000/api/v1/devices/?online=true
curl http://localhost:8000/api/v1/devices/?model=ULXD4D
```

**What this tests:**
- ✓ Device list endpoint
- ✓ Filtering by state
- ✓ Filtering by model
- ✓ Pagination
- ✓ Serialization

**Expected response:**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "ULXD4D @ 172.21.2.140",
      "model": "ULXD4D",
      "state": "ONLINE",
      "is_online": true,
      "firmware_version": "2.7.6.0",
      "serial_number": "4192900300"
    }
  ]
}
```

---

### Test 4: Test WebSocket Subscriptions (15 minutes)
```bash
# Terminal 1: Start polling
python manage.py poll_devices

# Terminal 2: Start dev server
python manage.py runserver

# Terminal 3: Subscribe to WebSocket
python scripts/test_websocket_subscription.py
# (This script will be created in Phase 3B)

# Watch real-time updates as devices change state
```

**Expected output:**
```
Connected to WebSocket
Subscribed to device updates
Waiting for events...
🔄 Event: Device ULXD4D @ 172.21.2.140 state changed to ONLINE
🔋 Battery: 92% | RF: -45 dBm
🔄 Event: Device ULXD4Q @ 172.21.0.96 state changed to ONLINE
...
```

---

## 📊 Test Dashboard

Check progress with:

```bash
# Health check (all systems)
python scripts/shure_api_health_check.py

# Monitor discovery
python scripts/shure_discovery_monitor.py

# View device count
python manage.py shell
>>> from micboard.models import Device
>>> Device.objects.count()
```

---

## 🔍 Debugging Common Issues

### Issue: "No devices discovered after polling"

**Diagnosis:**
```bash
# 1. Check Shure API has devices
python scripts/shure_api_health_check.py --full

# 2. Check database is clean
python manage.py shell
>>> from micboard.models import Device
>>> Device.objects.all().delete()
```

**Fix:**
1. Run model population test first
2. Then try polling

### Issue: "Models test says 0 devices"

**Diagnosis:**
```bash
# Check Shure API is working
python scripts/shure_discovery_monitor.py --duration 10

# Check API credentials
python scripts/shure_api_health_check.py
```

**Fix:**
- Verify MICBOARD_SHURE_API_SHARED_KEY is set
- Check Shure API service is running
- Check discovery IPs are configured

### Issue: "Poll command not creating devices"

**Diagnosis:**
```bash
# Check command syntax
python manage.py help poll_devices

# Check for errors
python manage.py poll_devices --verbosity 3

# Monitor API health while polling
python scripts/shure_api_health_check.py --full
```

---

## 📝 Test Checklist

```
Phase 3: Testing & Integration
[ ] Model population test passed
[ ] Polling command creates devices
[ ] API endpoints return device data
[ ] WebSocket subscriptions work
[ ] Real-time updates broadcast correctly
[ ] State changes persist to database
[ ] Telemetry data is stored
[ ] Filtering and search work
[ ] Performance acceptable
[ ] No crashes or errors
```

---

## 📈 Performance Baselines

Set these after testing:

```bash
# Device fetch time
time python scripts/test_micboard_shure_integration.py

# Poll time for 30 devices
time python manage.py poll_devices --duration 60

# API response time
curl -w "Time: %{time_total}s\n" http://localhost:8000/api/v1/devices/
```

**Expected:**
- Device fetch: < 2 seconds
- Poll cycle: < 5 seconds
- API response: < 200ms

---

## 🎓 Next Phase: Dashboard & UX (Phase 4)

Once Phase 3 is complete:

1. **Dashboard improvements:**
   - Real-time device counter
   - Battery/RF status indicators
   - Last updated timestamps
   - Online/offline indicators

2. **Frontend enhancements:**
   - Device filtering by model/location
   - Search functionality
   - Sort options
   - Export to CSV

3. **Admin interface:**
   - Bulk operations
   - State management
   - Assignment tools
   - Bulk discovery IP import

---

## 📞 Need Help?

### Check These First
1. [scripts/README_SHURE_SCRIPTS.md](scripts/README_SHURE_SCRIPTS.md) - Script usage
2. [docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md](docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md) - GUID issues
3. [docs/CONFIGURATION_CONSOLIDATED.md](docs/CONFIGURATION_CONSOLIDATED.md) - Configuration
4. [PHASE_2_COMPLETION.md](PHASE_2_COMPLETION.md) - Infrastructure status

### Commands
```bash
# Check everything
python scripts/shure_api_health_check.py --full

# Run with verbose output
python scripts/test_models_with_shure_data.py --sample-size 10

# Monitor in real-time
python scripts/shure_discovery_monitor.py --check-interval 2
```

---

**Start:** `python scripts/test_models_with_shure_data.py --sample-size 5`

**Then:** Monitor results and proceed to next test

**Goal:** All 4 tests passing ✅
