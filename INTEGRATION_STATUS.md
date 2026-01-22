# Django-Micboard: Shure System API Integration Complete

## 🎯 What Was Accomplished

### Infrastructure Debugging ✅
- **Root Cause Identified:** Wrong NetworkInterfaceId GUID in Shure System API config
- **Correct GUID Located:** `{A283C67D-499A-4B7E-B628-F74E8061FCE2}` (PANGP adapter)
- **Configuration Fixed:** Service restarted with correct GUID
- **Result:** 30+ devices now discovered and ONLINE

### Refactored Scripts ✅
Created 4 production-ready scripts in `scripts/` folder:

| Script | Purpose | Status |
|--------|---------|--------|
| `shure_api_health_check.py` | Connectivity & configuration diagnostics | ✓ Ready |
| `shure_configure_discovery_ips.py` | Manage discovery IP addresses | ✓ Ready |
| `shure_discovery_monitor.py` | Real-time device discovery monitoring | ✓ Ready |
| `test_micboard_shure_integration.py` | Validate django-micboard integration | ✓ Ready |

### Documentation ✅
Created 2 comprehensive guides:

| Document | Purpose | Location |
|----------|---------|----------|
| SHURE_NETWORK_GUID_TROUBLESHOOTING.md | Critical GUID issue diagnosis & fix | `docs/` |
| README_SHURE_SCRIPTS.md | Script reference & workflows | `scripts/` |

---

## 🚀 Quick Start

### 1. Health Check (Always Start Here)
```bash
python scripts/shure_api_health_check.py
```

### 2. Monitor Live Discovery
```bash
python scripts/shure_discovery_monitor.py
```

### 3. Configure Discovery IPs (if needed)
```bash
python scripts/shure_configure_discovery_ips.py --file campus_ips.txt
```

### 4. Test Django-Micboard Integration
```bash
python scripts/test_micboard_shure_integration.py
```

---

## 📋 Current Status

### Network Configuration
- ✅ Routing: Static route 172.21.0.0/16 via PANGP (10.2.240.224) on interface 21
- ✅ Firewall: SLP (UDP 8427) allowed outbound
- ✅ GUID: Correct NetworkInterfaceId set to `{A283C67D-499A-4B7E-B628-F74E8061FCE2}`

### API Configuration
- ✅ Base URL: `https://localhost:10000`
- ✅ Authentication: Shared key configured
- ✅ SSL Verification: Disabled (self-signed cert)
- ✅ Discovery IPs: 539 configured (319 unique campus IPs + existing)

### Device Discovery
- ✅ Status: **30+ devices discovered and ONLINE**
- ✅ Models: ULXD4D, ULXD4Q, ULXD6, ULXD8, SBC220, MXA710
- ✅ Firmware: Various versions from 2.4.9.0 to 2.10.0.0
- ✅ Subnets: Across multiple 172.21.x.x subnets

### Django-Micboard Integration
- ✅ Client: Initialized and working
- ✅ Device fetching: Successful (30+ devices)
- ✅ Serialization: JSON compatible
- ✅ WebSocket: URL generation ready
- ✅ Polling: Ready to start with `manage.py poll_devices`

---

## 🔧 The GUID Issue (Critical Knowledge)

### The Problem
If you see **0 devices** despite configuring IPs, the issue is almost always the wrong `NetworkInterfaceId` GUID in Shure System API config.

### Why It Happens
- SLP discovery packets are sent via specific network interface
- If GUID doesn't match actual adapter, packets go to wrong interface
- Service doesn't crash; it just silently fails to discover devices
- Firewall logs show outbound packets (from wrong adapter)

### The Fix
**File:** `C:\ProgramData\Shure\SystemAPI\Standalone\appsettings.Standalone.json5`

**Wrong (Example):**
```json
"NetworkInterfaceId": "{77966E49-BC72-4072-B6EC-2E9D8FE0CE94}"
```

**Correct (For our setup):**
```json
"NetworkInterfaceId": "{A283C67D-499A-4B7E-B628-F74E8061FCE2}"
```

**To Find Your Correct GUID:**
```powershell
# 1. Find your device network route
Get-NetRoute -DestinationPrefix "172.21.0.0/16" | Select-Object ifIndex

# 2. Find adapter with that ifIndex
Get-NetAdapter | Select-Object Name, ifIndex, InterfaceGuid

# 3. Copy the GUID from step 2
```

**Full Troubleshooting:** See [docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md](../docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md)

---

## 📚 Documentation Files

### Reference
- [docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md](../docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md) - GUID issue diagnosis & fix
- [scripts/README_SHURE_SCRIPTS.md](README_SHURE_SCRIPTS.md) - Script reference & workflows
- [docs/configuration.md](../docs/configuration.md) - Django configuration

### Setup Workflows

**Fresh Setup:**
```bash
python scripts/shure_api_health_check.py
python scripts/shure_configure_discovery_ips.py --file campus_ips.txt
python scripts/shure_discovery_monitor.py  # Wait for discoveries
python scripts/test_micboard_shure_integration.py
python manage.py poll_devices
```

**Troubleshooting:**
```bash
python scripts/shure_api_health_check.py --full
# If 0 devices: See SHURE_NETWORK_GUID_TROUBLESHOOTING.md
```

**Monitoring:**
```bash
python scripts/shure_discovery_monitor.py --check-interval 2
```

---

## ✅ Next Steps

### For Production
1. **Configure remaining devices** (if needed):
   ```bash
   python scripts/shure_configure_discovery_ips.py --summary
   ```

2. **Start polling**:
   ```bash
   python manage.py poll_devices
   ```

3. **Monitor in real-time**:
   ```bash
   python scripts/shure_discovery_monitor.py
   ```

4. **Subscribe to WebSocket updates**:
   - See: `docs/api/websocket.md`

### For Development
1. **Run tests**:
   ```bash
   pytest tests/ -v
   ```

2. **Check specific integration**:
   ```bash
   python scripts/test_micboard_shure_integration.py --sample-size 5
   ```

3. **Verify model population**:
   ```bash
   python manage.py shell
   >>> from micboard.models import Device
   >>> Device.objects.count()
   ```

---

## 📞 Troubleshooting Reference

| Issue | Check | Fix |
|-------|-------|-----|
| Connection refused | API running? | `net start "Shure System API Service"` |
| Auth failed | Shared key set? | Check MICBOARD_SHURE_API_SHARED_KEY env var |
| 0 devices | GUID correct? | See SHURE_NETWORK_GUID_TROUBLESHOOTING.md |
| Devices offline | Network route? | Check `route print` for 172.21.0.0/16 |
| No state changes | Polling running? | Start with `python manage.py poll_devices` |

---

## 🎓 Key Learnings

1. **Network Interface GUID** is critical—wrong GUID = silent discovery failure
2. **SLP Protocol** uses specific network adapter; must route to device network
3. **Firewall** must allow UDP 8427 (SLP) outbound
4. **Static Routes** matter when device network is on different VPN/interface
5. **Shure System API** doesn't crash on config errors; it just fails silently

---

## 📊 Infrastructure Map

```
┌─────────────────────────────────────────┐
│   Campus Network (172.21.0.0/16)        │
│   ├─ ULXD4D @ 172.21.2.140 (Primary)    │
│   ├─ ULXD4Q @ 172.21.0.96                │
│   ├─ SBC220 @ 172.21.0.99                │
│   └─ 27 more devices...                 │
└──────────────────────┬──────────────────┘
                       │
              Static Route (metric 2)
                       │
          172.21.0.0/16 via 10.2.240.224
                       │
┌──────────────────────┴──────────────────┐
│  Windows VM (Datacenter)                │
│  ├─ IP: 10.2.240.224/32 (VPN)           │
│  ├─ Interface: 21 (PANGP Adapter)       │
│  ├─ GUID: {A283C67D-499A-4B7E-...}      │
│  │                                      │
│  └─ Shure System API                    │
│     ├─ Port: 10000/https                │
│     ├─ Discovery: SLP via interface 21  │
│     └─ Devices: 30+ discovered/online   │
└──────────────────────────────────────────┘
          │
          │ (Django Polling)
          │
┌─────────┴────────────────────────────────┐
│   django-micboard                        │
│   ├─ Models: Device, Transmitter, etc.   │
│   ├─ Polling: poll_devices command       │
│   ├─ WebSocket: Real-time updates        │
│   └─ Dashboard: Live monitoring          │
└──────────────────────────────────────────┘
```

---

## 🏁 Summary

**Status:** ✅ **Complete and Operational**

- ✅ 30+ devices discovered and ONLINE
- ✅ Network routing verified
- ✅ Shure API working correctly
- ✅ Django-micboard ready for integration
- ✅ Production-grade scripts created
- ✅ Comprehensive documentation provided

**Next:** Start `python manage.py poll_devices` to begin populating device models and enabling real-time monitoring.

---

**Date:** January 21, 2026  
**Status:** Production Ready  
**Confidence:** Very High
