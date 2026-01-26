# Vendor-Agnostic Models Audit

**Date:** 2026-01-22
**Status:** Phase 1 Analysis Complete

## Executive Summary

Analyzed all models in `micboard/models/` for vendor-specific dependencies. Overall assessment: **Models are largely vendor-agnostic** with manufacturer abstraction handled through the `Manufacturer` ForeignKey and plugin architecture.

## Findings

### ✅ Well-Abstracted Models

#### Receiver Model (`receiver.py`)
- **Status:** Vendor-agnostic ✓
- **Design:** Uses `manufacturer` ForeignKey for vendor association
- **Device Types:** Current types (`uhfr`, `qlxd`, `ulxd`, `axtd`, `p10t`) are Shure-specific but stored as generic strings
- **Recommendation:** Keep as-is. Device types should be managed by plugin `DEVICE_TYPES` registry, not hardcoded

**Key Fields:**
```python
manufacturer = ForeignKey("micboard.Manufacturer")  # Vendor abstraction
api_device_id = CharField()  # Vendor API identifier
device_type = CharField(choices=DEVICE_TYPES)  # Generic type field
```

#### Transmitter Model (`transmitter.py`)
- **Status:** Vendor-agnostic ✓
- **Design:** All fields are generic RF/battery metrics
- **Fields:** battery, rf_level, frequency, signal quality - all vendor-neutral

#### Channel Model (`channel.py`)
- **Status:** **Needs Documentation Update**
- **Issue:** Docstring says "Represents an individual channel on a Shure wireless receiver"
- **Recommendation:** Update docstring to be vendor-neutral:
  ```python
  """Represents an individual channel on a wireless receiver."""
  ```

### 🔧 Configuration Models (Expected Vendor-Specific)

#### Manufacturer Model (`configuration.py`)
- **Status:** Correct vendor-specific usage ✓
- **Purpose:** Stores vendor codes and API configuration
- **Examples in help_text:** `'shure'`, `'sennheiser'` - appropriate for configuration

#### Discovery Models (`discovery.py`)
- **Status:** Correct vendor examples ✓
- **Purpose:** Track discovered devices by manufacturer
- **Design:** Uses `manufacturer` ForeignKey and `manufacturer_code` for filtering

#### ShureCidrRange Model (`discovery.py`)
- **Status:** **Vendor-Specific Model Name**
- **Issue:** Model name hardcodes "Shure" manufacturer
- **Usage:** Stores CIDR ranges for Shure discovery scans
- **Recommendation:** Consider renaming to `DiscoveryCidrRange` with manufacturer ForeignKey in future refactor
- **Priority:** LOW - functional as-is, breaking change required

### 📊 Summary Matrix

| Model | Vendor-Agnostic | Action Required | Priority |
|-------|-----------------|-----------------|----------|
| Receiver | ✅ Yes | None | - |
| Transmitter | ✅ Yes | None | - |
| Channel | ⚠️ Mostly | Update docstring | LOW |
| Charger | ✅ Yes | None | - |
| Location | ✅ Yes | None | - |
| Groups | ✅ Yes | None | - |
| Telemetry | ✅ Yes | None | - |
| UserProfile | ✅ Yes | None | - |
| Manufacturer | ✅ Yes (by design) | None | - |
| DiscoveredDevice | ✅ Yes | None | - |
| ShureCidrRange | ❌ No | Rename (future) | LOW |

## Recommendations

### Immediate Actions (This Phase)

1. **Update Channel Docstring**
   - Change: "Represents an individual channel on a Shure wireless receiver"
   - To: "Represents an individual channel on a wireless receiver"

### Future Considerations (Post-Phase 2)

2. **Receiver DEVICE_TYPES Registry**
   - Move hardcoded Shure types to plugin-level registry
   - Allow plugins to register supported device types
   - Keep model field generic: `device_type = CharField()`

3. **ShureCidrRange Rename** (Breaking Change)
   - Rename to: `DiscoveryCidrRange`
   - Add: `manufacturer = ForeignKey("Manufacturer")`
   - Requires: Data migration for existing Shure ranges

4. **Plugin Device Type Discovery**
   - Implement: `ManufacturerPlugin.get_supported_device_types()`
   - Return: `[{"code": "ulxd", "name": "ULX-D"}, ...]`
   - Use: Populate UI dropdowns, validate API responses

## Architecture Validation

The current architecture **correctly implements vendor abstraction** through:

1. **Manufacturer ForeignKey Pattern**
   ```python
   manufacturer = models.ForeignKey("micboard.Manufacturer")
   ```
   - Used in: Receiver, DiscoveredDevice, ManufacturerConfiguration
   - Enables multi-manufacturer support without model changes

2. **Plugin Architecture**
   - Location: `micboard/manufacturers/{vendor}/`
   - Handles vendor-specific API logic
   - Models remain generic data containers

3. **Generic Field Names**
   - `api_device_id` (not `shure_device_id`)
   - `device_type` (not `shure_model`)
   - `firmware_version` (not `shure_firmware`)

## Conclusion

**Models are well-designed for multi-manufacturer support.** Only minor documentation update needed (Channel docstring). The `ShureCidrRange` model name is the only true vendor-specific naming issue, but it's low priority and functional as-is.

The plugin architecture successfully isolates vendor-specific logic from the data layer.

---

**Next Steps:**
1. Fix Channel docstring
2. Document plugin device type registry pattern for Phase 2
3. Plan ShureCidrRange migration for future major version
