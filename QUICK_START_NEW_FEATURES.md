# Quick Start: New Features

## Overview
This document covers the three new features just implemented:
1. **Manufacturer API Server Management** - Manage multiple Shure API servers across locations
2. **Field Unit Accessories** - Track lav mics, packs, IEM earbuds, etc.
3. **Hardware Inventory Gap Analysis** - Dashboard showing missing data

---

## 1. Manufacturer API Server Management

### What It Does
Allows you to add and manage multiple manufacturer API servers (e.g., Shure System API instances) per location, with health checks and enable/disable controls.

### How to Use

#### Access Admin
- Go to `/admin/`
- Click **Manufacturer API Servers** in the left sidebar

#### Add a Server
1. Click **Add Manufacturer API Server**
2. Fill in:
   - **Name**: Friendly name (e.g., "Main Venue", "Branch Office")
   - **Manufacturer**: Select "Shure System API"
   - **Base URL**: Your API endpoint (e.g., `https://api.venue.local:10000`)
   - **Shared Key**: Your API authentication key
   - **Verify SSL**: Check/uncheck based on your setup
   - **Location**: Physical location name (optional, for reference)
   - **Enabled**: Toggle to enable/disable
3. Click **Save**

#### Test Connection
1. Select one or more servers from the list
2. Click the **Test connection to API servers** action dropdown
3. Click **Go**
4. Results will show in the status message
5. Status field will update to "Active" or "Error" with details

#### Enable/Disable Servers
1. Select servers from list
2. Use dropdown actions:
   - **Enable selected servers** - Turns them on
   - **Disable selected servers** - Turns them off
3. Click **Go**

### Use Cases

**Multi-Venue Setup:**
```
Venue Main (Active)      → https://api1.venue.local:10000
Venue Backup (Inactive)  → https://api2.venue.local:10000
Venue Remote (Active)    → https://api3.remote.local:10000
```

**Rollout Testing:**
- Enable one server to test
- Disable for maintenance
- Test failover scenario

**High Availability:**
- Primary + backup servers
- Health checks monitor both
- Admins can quickly switch if one fails

---

## 2. Field Unit Accessories

### What It Does
Track all field unit equipment: lav microphones, wireless packs, IEM earbuds, cables, mounts, cases, etc.

### How to Use

#### View All Accessories
1. Go to `/admin/`
2. Click **Accessories** in left sidebar
3. Browse list with colors for categories and condition

#### Add Accessory to a Device
1. Go to **Wireless Chassis** in admin
2. Find a receiver/device
3. Click on it to edit
4. Scroll to **Accessories** section (inline table)
5. Click **Add another Accessory**
6. Fill in:
   - **Category**: Microphone, Pack, IEM Earbuds, etc.
   - **Name**: Model/description (e.g., "Shure SM7B", "Sennheiser EW Pack")
   - **Assigned To**: Performer/role (e.g., "Lead Singer", "Stage Manager")
   - **Condition**: Excellent/Good/Fair/Needs Repair/Unknown
   - **Available**: Checkbox to mark if usable
   - **Serial Number**: For inventory tracking (optional)
   - **Checked Out**: When assigned out
   - **Checked In**: When returned
   - **Notes**: Any issues or maintenance notes (e.g., "Screen cracked but functional")
7. Click **Save**

#### Bulk Assign Condition
1. Go to **Accessories** list
2. Select multiple accessories
3. From dropdown:
   - **Mark as available** - All working
   - **Mark as unavailable** - Broken/missing
   - **Mark as needs repair** - Flagged for service
4. Click **Go**

#### Filter & Search
- **By Category**: Microphone, Pack, Earbuds, etc.
- **By Condition**: Excellent, Good, Fair, Needs Repair
- **By Availability**: Available / Unavailable
- **By Device**: Which receiver they're attached to
- **Search**: By name, serial number, or performer

### Categories

| Category | Examples |
|----------|----------|
| Microphone | Shure SM7B, SM4B, Sennheiser |
| Pack | Bodypack transmitter, Belt pack |
| IEM Earbuds | Monitor earbuds, wireless earbuds |
| Antenna | Diversity antenna, booster antenna |
| Cable | XLR cable, USB, adapter cables |
| Power | Battery charger, power supply |
| Mount | Mic stand adapter, cable clip |
| Case | Foam case, hard case, cable case |
| Other | Miscellaneous equipment |

### Conditions

- **Excellent**: Perfect condition
- **Good**: Working well, minor cosmetic wear
- **Fair**: Working but showing age/wear
- **Needs Repair**: Known issues, flagged for service
- **Unknown**: Not yet assessed

---

## 3. Hardware Inventory Gap Analysis

### What It Does
Dashboard showing where your inventory has missing or incomplete data.

### How to Use

#### Access Dashboard
1. Go to `/admin/`
2. Look for **Hardware Gap Analysis** (or navigate directly)
3. View live report

#### Key Metrics

**Core Data Gaps**
- % devices missing IP address
- % devices missing serial number
- % devices missing model info
- % devices missing manufacturer

**Accessory Gaps**
- How many devices have NO accessories
- Breakdown of accessory types
- How many accessories need repair
- How many marked unavailable

**Device Model Analysis**
- For each model (ULXD4Q, SBC220, etc.):
  - Total count
  - Average accessories per unit
  - How many missing IP address
  - How many without ANY accessories

**Health Check Status**
- Number of devices never polled

### What to Fix

**High Priority (All devices should have these):**
- IP Address
- Device Serial Number
- Manufacturer
- At least basic model identification

**Medium Priority (Improves operations):**
- Accessories documented (especially mics/packs)
- Accessory serial numbers tracked
- Performer assignments

**Low Priority (Informational):**
- Accessory checkout dates
- Detailed condition notes

### Using the Report

1. **Identify gaps**: Which data fields are most commonly missing?
2. **Plan work**: "We're missing 45% IP addresses - need to run discovery"
3. **Prioritize**: "10 devices need repair - schedule maintenance"
4. **Export**: Copy data for reports/presentations

---

## Configuration for Multi-Location

### Django Settings

In `example_project/settings.py`:

```python
MANUFACTURER_API_SERVERS = {
    "main_venue": {
        "manufacturer": "shure",
        "base_url": "https://api.main.local:10000",
        "shared_key": "YOUR_SHARED_KEY_HERE",
        "verify_ssl": False,
        "location_name": "Main Venue - Stage",
        "enabled": True,
    },
    "backup_venue": {
        "manufacturer": "shure",
        "base_url": "https://api.backup.local:10000",
        "shared_key": "YOUR_BACKUP_KEY_HERE",
        "verify_ssl": False,
        "location_name": "Backup Venue - Archive",
        "enabled": False,
    },
}
```

### Import Devices from Specific Server

```bash
# Import from a specific server
python manage.py import_shure_devices --server-id main_venue --full

# Dry run to preview first
python manage.py import_shure_devices --server-id main_venue --dry-run
```

---

## Common Workflows

### Setup New Venue

1. **Add API Server** (Admin > Manufacturer API Servers)
   - Enter venue name and API endpoint
   - Test connection
   - Enable

2. **Import Devices** (Management Command)
   ```bash
   python manage.py import_shure_devices --server-id venue_name --full
   ```

3. **Review Imports** (Admin > Wireless Chassis)
   - Check device counts by model
   - Look for any missing IPs

4. **Add Accessories** (Admin > Accessories)
   - For each receiver that will be used on-site
   - Document what mics/packs are available

### Track Show Setup

1. **Assign Accessories** (Admin > Wireless Chassis > Accessories)
   - Add performer names
   - Mark as checked out

2. **Monitor Condition** (Admin > Accessories)
   - Filter by "Needs Repair"
   - Update condition after use

3. **Return & Update** (Admin > Accessories)
   - Mark checked in
   - Update condition if needed

---

## Performance Tips

- **For large deployments (100+ devices):**
  - Use filters before bulk actions
  - Search by device model first
  - Consider pagination in list views

- **Gap Analysis:**
  - Run during off-hours if very large
  - Export results for reports

- **Multi-Server Testing:**
  - Start with one server in dry-run mode
  - Enable servers one at a time
  - Monitor health checks closely

---

## Troubleshooting

**Server Connection Test Fails:**
- Verify SSL certificate if `verify_ssl=True`
- Check shared key matches what API expects
- Confirm API endpoint is accessible from server
- Check firewall rules

**Accessories Not Appearing:**
- Refresh page (browser cache)
- Verify WirelessChassis model was saved
- Check for FK errors in database

**Gap Analysis Missing Data:**
- Run `python manage.py check` to verify schema
- Ensure devices have been imported
- Check that nullable fields are actually NULL (not empty string)

---

## Related Commands

```bash
# Check overall system health
python manage.py check

# Import Shure devices
python manage.py import_shure_devices --full

# Create new API server config
python manage.py

# View accessory report
# (Go to /admin/integrations/accessory/)
```

---

## What's Next?

After implementing these features, typical next steps:

1. **Testing:** Add test API servers and accessories to try everything
2. **Live Deployment:** Configure actual venues in production
3. **Automation:** Consider periodically scheduled imports
4. **Reporting:** Export gap analysis for inventory audits
5. **Mobile:** Plan mobile accessory checkout app
6. **Integration:** Connect to venue management system
