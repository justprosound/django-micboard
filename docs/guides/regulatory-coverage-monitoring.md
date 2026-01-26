# Regulatory Coverage Monitoring

## Overview

Django Micboard includes automatic monitoring and alerting for RF channels operating without regulatory frequency data coverage. This helps ensure compliance and data completeness.

## Architecture Understanding

**Three-layer RF coordination architecture with regulatory compliance at each level:**

```
WirelessChassis (Base Station)
    ↓ has band plan (frequency RANGE - what it CAN operate on)
    ↓ regulatory check: band plan coverage
RFChannel (RF Slot/Channel)
    ↓ has frequency assignment (specific FREQUENCY - what it IS doing)
    ↓ regulatory check: frequency coverage (PRIMARY COORDINATION)
WirelessUnit (Field Device)
    ↓ reports what it receives
    ↓ delegates to RFChannel
```

**Regulatory Compliance Layers:**

1. **WirelessChassis Band Plan** (Foundational)
   - Example: Shure ULXD4Q band G50 operates 470-534 MHz
   - Checks: Is the entire band plan range allowed in this regulatory domain?
   - Impact: Determines what frequencies the chassis CAN be coordinated to

2. **RFChannel Frequency** (Primary Coordination)
   - Example: Channel 1 assigned to 520.125 MHz
   - Checks: Is this specific frequency allowed in this regulatory domain?
   - Impact: The actual coordinated frequency being used

3. **WirelessUnit** (Secondary/Reporting)
   - Example: Handheld mic reports 520.125 MHz
   - Checks: Delegates to assigned RFChannel
   - Impact: Field device reflects coordinated frequency

## Features

### 1. WirelessChassis Band Plan Checks (Foundational)

The `WirelessChassis` model includes band plan regulatory checking:

#### Methods Available on WirelessChassis

**`get_regulatory_domain()`**
- Returns the applicable `RegulatoryDomain` based on chassis location
- Checks location.regulatory_domain first, then country code lookup

**`has_band_plan()`**
- Returns True if chassis has band plan configured (min/max MHz)

**`has_band_plan_regulatory_coverage()`**
- Returns `True` if the entire band plan range is covered by regulatory data
- Returns `False` if no band plan, no regulatory domain, or insufficient coverage

**`needs_band_plan_regulatory_update` (property)**
- Flags online chassis with band plans that lack regulatory coverage
- Used to trigger admin alerts

**`get_band_plan_regulatory_status()`**
- Returns comprehensive status dictionary including:
  - `has_band_plan`: bool
  - `has_coverage`: bool
  - `regulatory_domain`: str (domain code like 'FCC', 'ETSI')
  - `band_plan_range`: str (human-readable range with name)
  - `needs_update`: bool
  - `message`: str (human-readable status)

**Band Plan Fields:**
- `band_plan_min_mhz`: Float - Minimum frequency (MHz)
- `band_plan_max_mhz`: Float - Maximum frequency (MHz)
- `band_plan_name`: String - Band identifier (e.g., "G50 470-534MHz", "UHF Band IV")

### 2. RFChannel Regulatory Checks (Primary Coordination)

The `RFChannel` model includes frequency-specific regulatory checking:

### 1. RFChannel Regulatory Checks (Primary)

The `RFChannel` model includes comprehensive regulatory checking methods:

#### Methods Available on RFChannel

**`get_regulatory_domain()`**
- Returns the applicable `RegulatoryDomain` based on chassis location
- Checks chassis.location.regulatory_domain first, then country code lookup

**`has_regulatory_coverage()`**
- Returns `True` if the channel's frequency is covered by regulatory data
- Returns `False` if no coverage exists

**`needs_regulatory_update` (property)**
- Flags active channels operating without regulatory coverage
- Used to trigger admin alerts

**`get_regulatory_status()`**
- Returns comprehensive status dictionary including:
  - `has_coverage`: bool
  - `regulatory_domain`: str (domain code like 'FCC', 'ETSI')
  - `operating_frequency_mhz`: float (the coordinated frequency)
  - `needs_update`: bool
  - `message`: str (human-readable status)

### 2. WirelessUnit Delegation (Secondary)

`WirelessUnit` devices delegate regulatory checks to their assigned RFChannel:

**`get_assigned_rf_channel()`**
- Returns the RFChannel this unit is assigned to
- Returns None if no channel assigned

**`get_regulatory_status()`**
- Delegates to assigned RFChannel's `get_regulatory_status()`
- Returns "no channel assigned" status if not linked to any channel
- Includes `source: "rf_channel"` or `source: "no_channel"` in response

### 4. Django Admin Integration

The Django admin interface displays regulatory status at all three levels:

**Wireless Chassis Admin (`/admin/micboard/wirelesschassis/`)** - FOUNDATIONAL
- New "Band Plan" column shows configured frequency range
- New "Band Plan Regulatory Status" column shows:
  - ✅ OK - Green when band plan is covered
  - ⚠️ Missing coverage - Red when band plan lacks regulatory data
  - ℹ️ No band plan - Gray when not configured

**RF Channels Admin (`/admin/micboard/rfchannel/`)** - PRIMARY COORDINATION
- "Regulatory Status" column shows:
  - ✅ OK (frequency MHz) - Green for covered
  - ⚠️ Missing coverage - Red for channels needing updates
  - ℹ️ No frequency - Gray for channels without frequency assignment

**Wireless Units Admin (`/admin/micboard/wirelessunit/`)** - SECONDARY (delegates)
- Regulatory status delegates to assigned RFChannel
- Shows "Via RFChannel N: [status]" when channel assigned
- Shows "No RF channel assigned" when not linked

### 5. Audit Management Command

A management command audits all three levels:

```bash
python manage.py audit_regulatory_coverage
```

**Options:**
- `--verbose` - Show detailed information for each device
- `--show-ok` - Display devices with OK coverage (default: only shows issues)

**Output Example:**
```
================================================================================
REGULATORY COVERAGE AUDIT
================================================================================

Architecture: Chassis (band plan) → RFChannel (frequency) → WirelessUnit
RF coordination happens at RFChannel level (frequency assignment).
Band plan compliance checked at Chassis level (operating range).

🏢 WIRELESS CHASSIS (Foundational - Band Plan Coverage)
--------------------------------------------------------------------------------
  ⚠️  [CHASSIS] Shure ULXD4Q (receiver) - Main Rack 1 - ⚠️ Band plan G50 (470.0-534.0 MHz) not covered by FCC regulatory data - admin needs to update
  ✅  [CHASSIS] Sennheiser EM 6000 (receiver) - Side Stage - ✅ Band plan regulatory coverage OK (ETSI)

  Total online chassis: 12
  ✅ OK: 10
  ℹ️  No band plan: 1
  ⚠️  Needs update: 1

📻 RF CHANNELS (Primary - Where Coordination Happens)
--------------------------------------------------------------------------------
  ⚠️  ULXD4D-1 - RF Ch 1 (Receive) - ⚠️ Frequency 795.0 MHz not covered by FCC regulatory data - admin needs to update

  Total active channels: 48
  ✅ OK: 47
  ℹ️  No frequency: 0
  ⚠️  Needs update: 1

📡 WIRELESS UNITS (Secondary - Delegates to RF Channels)
--------------------------------------------------------------------------------
  ℹ️  Bodypack 5 (Microphone Transmitter) - Slot 5 - ℹ️ No RF channel assigned - regulatory check not applicable

  Total active units: 45
  ✅ OK (via RF channel): 43
  ℹ️  No RF channel: 2
  ⚠️  Needs update: 0

================================================================================
SUMMARY
================================================================================
⚠️  2 issue(s) need regulatory data updates:
     - 1 chassis band plan(s)
     - 1 RF channel(s)

ACTION REQUIRED:
  1. Review chassis band plans and RF channels flagged above
  2. Run: python manage.py import_efis_regulations --force
  3. Or manually add frequency bands in Django admin for missing regions
  4. Update chassis band plan fields if devices have band info
```

## Workflow

### RF Coordination Architecture

Understanding the three-layer data flow:

```
1. WirelessChassis discovered → Band plan info stored (what it CAN do)
2. RFChannel created → Static channel assignment on chassis
3. Frequency coordinated → RFChannel.frequency set (what it IS doing - COORDINATION HAPPENS HERE)
4. WirelessUnit linked → Field device assigned to RFChannel
5. Regulatory checks:
   a. Band plan check → Validates chassis band_plan_min/max_mhz against regulatory bands
   b. Frequency check → Validates RFChannel.frequency against regulatory bands (primary)
   c. Unit check → Delegates to assigned RFChannel
```

### When Band Plans & Frequencies Are Assigned

1. **Chassis discovered** with band plan information (e.g., G50 470-534MHz)
2. **Band plan stored** in `band_plan_min_mhz`, `band_plan_max_mhz`, `band_plan_name` fields
   - **Auto-population available**: Use Django admin dropdown to select standard band plans (see [Band Plan Auto-Population Guide](band-plan-auto-population.md))
   - Frequencies auto-fill from registry for Shure, Sennheiser, Lectrosonics, Wisycom, Audio-Technica, Sony
   - Bulk updates supported for multiple chassis
3. **Band plan validated** - Check if operating range is allowed in regulatory domain
4. **RF channels created** when chassis discovered
5. **Frequency coordination happens** - Admin or automation assigns specific frequencies to RFChannels
6. **Frequency validated** - Check if specific frequency is allowed in regulatory domain
7. **Admin sees alerts** in Django admin for both band plan and frequency coverage issues

### Resolving Missing Coverage

**Option 1: Import EFIS Data (European frequencies)**
```bash
python manage.py import_efis_regulations --force
```
This imports the latest European regulatory data from CEPT EFIS API.

**Option 2: Manual Entry (Non-European or custom)**
1. Navigate to Django Admin → RF Coordination → Regulatory Domains
2. Add or update the relevant domain (e.g., 'FCC', 'ACMA')
3. Add frequency bands under that domain
4. Re-run audit: `python manage.py audit_regulatory_coverage`

**Option 3: Update Chassis Location**
If the chassis location has wrong or missing regulatory domain:
1. Django Admin → Locations → Building
2. Find the building/location where chassis is deployed
3. Set the correct `regulatory_domain` or `country` field
4. Re-run audit

**Option 4: Add/Update Chassis Band Plan**
If chassis is missing band plan information:
1. Django Admin → Wireless Chassis
2. Find the chassis device
3. Set `band_plan_min_mhz`, `band_plan_max_mhz`, and `band_plan_name`
   - Example for Shure ULXD G50: min=470, max=534, name="G50 470-534MHz"
   - Example for Sennheiser Aw+: min=470, max=558, name="Aw+ 470-558MHz"
4. Re-run audit to verify coverage

### Monitoring in Production

**Scheduled Audit:**
Add to your cron/scheduled tasks:
```bash
# Daily audit at 6am
0 6 * * * cd /path/to/project && .venv/bin/python manage.py audit_regulatory_coverage --verbose >> /var/log/micboard/regulatory_audit.log 2>&1
```

**Integration with Monitoring Tools:**
The audit command exits with:
- Exit code 0: All devices OK
- Console output parseable for log monitoring

## Data Model

### RegulatoryDomain
- `code`: Domain identifier (e.g., 'FCC', 'ETSI', 'ACMA')
- `country_code`: ISO 3166-1 alpha-2 (e.g., 'US', 'DE', 'AU')
- `min_frequency_mhz` / `max_frequency_mhz`: General frequency bounds

### FrequencyBand
- `regulatory_domain`: FK to RegulatoryDomain
- `start_frequency_mhz` / `end_frequency_mhz`: Specific band range
- `band_type`: 'allowed', 'restricted', 'forbidden', 'guard'
- `name`: Band description (e.g., 'UHF TV Band IV')

### Device Frequency Fields
- `RFChannel.frequency`: FloatField - **WHERE RF COORDINATION HAPPENS** (primary)
- `WirelessUnit.frequency`: CharField - Reported value from device (secondary, echoes RFChannel)

## API Integration

The regulatory status is available programmatically:

```python
from micboard.models import RFChannel, WirelessUnit

# Check an RF channel (primary - where coordination happens)
channel = RFChannel.objects.get(pk=1)
status = channel.get_regulatory_status()
print(status)
# {
#     'has_coverage': False,
#     'regulatory_domain': 'FCC',
#     'operating_frequency_mhz': 520.5,
#     'needs_update': True,
#     'message': '⚠️ Frequency 520.5 MHz not covered by FCC regulatory data - admin needs to update'
# }

# Flag for alerting
if channel.needs_regulatory_update:
    send_alert_to_admin(channel)

# Check a wireless unit (delegates to RF channel)
unit = WirelessUnit.objects.get(pk=1)
status = unit.get_regulatory_status()
print(status)
# {
#     'has_coverage': False,
#     'regulatory_domain': 'FCC',
#     'operating_frequency_mhz': 520.5,
#     'needs_update': True,
#     'source': 'rf_channel',
#     'message': 'Via RFChannel 1: ⚠️ Frequency 520.5 MHz not covered...'
# }
```

## Best Practices

1. **Run EFIS import regularly** (weekly) to keep European data current
2. **Audit after RF coordination changes** to catch missing coverage early
3. **Monitor audit logs** for trends in missing coverage
4. **Document custom frequency bands** for non-European regions
5. **Set location regulatory domains** proactively during chassis deployment
6. **Focus on RFChannel compliance** - that's where coordination happens

## Future Enhancements

Potential additions:
- Automated alerting via email/Slack when devices need updates
- Dashboard widget showing regulatory coverage percentage
- Bulk import for FCC/ACMA/other regional data
- Frequency coordination recommendations based on regulatory bands
- Integration with RF scan file imports for venue-specific constraints

## Related Documentation

- [EFIS Import Guide](../integration/efis-import.md) - European frequency data import
- [RF Coordination Overview](../guides/rf-coordination.md) - Frequency management concepts
- [Location Setup](../guides/location-setup.md) - Configuring buildings and regulatory domains
