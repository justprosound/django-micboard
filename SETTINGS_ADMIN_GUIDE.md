# Settings Management - Admin Quick Reference

## Overview

The Settings system allows you to configure how django-micboard behaves **without editing any code**. All changes take effect immediately.

---

## 🚀 Getting Started (5 Minutes)

### 1. Access Settings Admin
- Go to your Django admin panel
- Look for **"Micboard"** section
- Click **"Settings"** or **"Setting Definitions"**

### 2. Common Tasks

#### Configure Battery Thresholds for a Manufacturer

1. Go to **Micboard → Settings → Add Setting**
2. Select **Definition**: "Battery Good Level (%)"
3. Select **Scope**: "Manufacturer"
4. Select **Manufacturer**: Choose your device brand (Shure, Sennheiser, etc.)
5. Enter **Value**: e.g., `90`
6. Click **Save**

💡 **Repeat for:**
- Battery Low Level (%)
- Battery Critical Level (%)

#### Configure Polling Interval

1. Go to **Micboard → Settings → Add Setting**
2. Select **Definition**: "Polling Interval (seconds)"
3. Select **Scope**: "Organization"
4. Select **Organization**: Choose your company
5. Enter **Value**: e.g., `300` (5 minutes)
6. Click **Save**

#### Use Bulk Configuration Tool

For faster setup of multiple manufacturer settings:

1. Go to **Admin → Settings → Bulk Configuration** (or `/admin/settings/bulk/`)
2. Select the **Scope** (usually "Manufacturer")
3. Select the manufacturer to configure
4. Fill in the fields you want to change
5. Click **Save** - all update at once!

---

## 📋 Common Settings Reference

### Battery Levels (Manufacturer-Specific)

**Where**: Manufacturer scope (Shure, Sennheiser, etc.)

| Setting | Typical Value | Notes |
|---------|---------------|-------|
| Battery Good Level | 90 | Device considered healthy |
| Battery Low Level | 20 | Alert when below this |
| Battery Critical Level | 0-5 | Device may fail |

*Shure defaults: Good=90, Low=20, Critical=0*
*Sennheiser defaults: Good=85, Low=25, Critical=5*

### API Health Checks (Manufacturer-Specific)

**Where**: Manufacturer scope

| Setting | Typical Value | Notes |
|---------|---------------|-------|
| Health Check Interval | 300 seconds | Check every 5 minutes |
| API Timeout | 30 seconds | Max wait for response |
| Max Devices Per Call | 100 | Batch size for API |

### Features (Manufacturer-Specific)

**Where**: Manufacturer scope

| Setting | Options | Notes |
|---------|---------|-------|
| Supports Discovery IPs | true/false | Can find by subnet IP? |
| Supports Health Check | true/false | Has health API? |

### Organization Settings

**Where**: Organization scope (applies to your MSP or tenant)

| Setting | Typical Value | Notes |
|---------|---------------|-------|
| Discovery Enabled | true | Auto-find new devices |
| Polling Enabled | true | Auto-monitor devices |
| Polling Interval | 300 seconds | How often to check status |
| Polling Batch Size | 50 | Devices per poll batch |
| Log API Calls | false | Keep detailed API logs? |

---

## 🎯 Setting Types Explained

When you enter a value, the system validates it based on type:

| Type | How to Enter | Examples |
|------|-------------|----------|
| **String** | Any text | `"my-config"`, `"device-name"` |
| **Integer** | Whole number | `300`, `90`, `50` |
| **Boolean** | Yes/No equivalent | `true`, `false` (or `yes`, `no`, `1`, `0`) |
| **JSON** | Formatted JSON | `{"key": "value", "count": 42}` |
| **Choices** | Dropdown menu | (Admin shows available options) |

---

## 🔍 Scope Hierarchy (How Values Are Resolved)

Settings are looked up in this order. The **first one found** is used:

```
1. Manufacturer-specific setting (if applicable)
   ↓ if not found
2. Site-specific setting (if applicable)
   ↓ if not found
3. Organization-specific setting
   ↓ if not found
4. Global setting
   ↓ if not found
5. Default value (built into system)
```

**Example**: Battery low threshold for Shure microphones at NYC site:
1. Check if **NYC Site** has a Shure battery setting → **NOT found**
2. Check if **Your Organization** has a Shure battery setting → **Found: 22%** ✓ **USE THIS**
3. (Would check global, then default, but we already found it)

---

## ✅ Step-by-Step: Configure Your Manufacturer

### Scenario: Set up Shure devices

#### Step 1: Battery Configuration
1. Click **Add Setting** (Admin → Setting)
2. **Definition**: "Battery Good Level (%)" → Set to **90**
3. **Manufacturer**: Shure → **Save**

4. Click **Add Setting** again
5. **Definition**: "Battery Low Level (%)" → Set to **20**
6. **Manufacturer**: Shure → **Save**

7. Click **Add Setting** again
8. **Definition**: "Battery Critical Level (%)" → Set to **5**
9. **Manufacturer**: Shure → **Save**

#### Step 2: API Configuration
1. Click **Add Setting**
2. **Definition**: "API Timeout (seconds)" → Set to **30**
3. **Manufacturer**: Shure → **Save**

2. Click **Add Setting**
3. **Definition**: "Max Devices Per API Call" → Set to **100**
4. **Manufacturer**: Shure → **Save**

#### Step 3: Feature Flags
1. Click **Add Setting**
2. **Definition**: "Supports Discovery IPs" → Set to **true**
3. **Manufacturer**: Shure → **Save**

2. Click **Add Setting**
3. **Definition**: "Supports Health Check API" → Set to **true**
4. **Manufacturer**: Shure → **Save**

✅ **Done! Shure is now configured.**

---

## 🔄 When Changes Take Effect

| Change Type | When Applied |
|-------------|--------------|
| Via Django Admin UI | Immediately |
| Via Bulk Configuration | Immediately |
| Programmatic (API) | Immediately |

**Cache Note**: The system caches settings for **5 minutes** for performance. If you need changes to take effect faster:

1. Go to **Settings Definition** admin
2. Click the setting you changed
3. The cache will refresh automatically
4. Or wait 5 minutes and it auto-refreshes

---

## ⚠️ Common Mistakes & Fixes

### Problem: Setting Shows Wrong Value
**Solution**:
- Check scope - you might be looking at the wrong organization/manufacturer
- Wait 5 minutes for cache refresh
- Clear browser cache (Ctrl+F5)

### Problem: Setting Saves but Doesn't Work
**Solution**:
- Verify correct **Scope** selected
- Verify correct **Manufacturer/Organization** selected
- Check **Data Type** matches (number vs text)
- Test with **Bulk Configuration** tool

### Problem: Can't Find Setting Definition
**Solution**:
1. Go to **Setting Definition** admin
2. Search for the setting name
3. Make sure it's marked **Active** (green checkmark)
4. If missing, click **Initialize Settings** (or run `python manage.py init_settings`)

### Problem: Old Value Still Being Used
**Solution**:
1. Verify you saved the setting (page should show "Setting updated")
2. Wait 5 minutes for cache to expire
3. Or contact your developer to clear the cache

---

## 📊 View All Configured Settings

### Method 1: Overview Dashboard
1. Go to **Admin → Settings → Overview**
2. See all settings grouped by scope
3. Click any setting to edit

### Method 2: Admin Filter
1. Go to **Admin → Settings**
2. Use **Filters** on right side:
   - Filter by **Scope** (Manufacturer, Organization, etc.)
   - Filter by **Setting Type** (Boolean, Integer, etc.)
3. Search by key or value

---

## 🛠️ For System Administrators

### First Time Setup

```bash
# Initialize all settings
python manage.py init_settings --manufacturer-defaults

# Verify
# Go to Admin → Setting Definition
# Should see 17 settings listed
```

### Reset to Defaults

```bash
# WARNING: Deletes all configured settings!
python manage.py init_settings --reset
```

### Check Settings Value

1. Go to **Admin → Settings**
2. Search by **Definition** name
3. Click to view value and scope

### Disable a Setting

1. Go to **Admin → Setting Definition**
2. Find the setting
3. Uncheck **Active**
4. Save

When disabled, the setting won't appear in forms for new configurations.

---

## 📚 What Values Should I Set?

### Battery Levels
- **Good%**: When battery is healthy (usually 80-95%)
- **Low%**: When to show warning (usually 15-30%)
- **Critical%**: When device may stop working (usually 0-10%)

*These vary by device brand - check manufacturer specs*

### API Timeouts
- **Timeout**: How long to wait for manufacturer API response (usually 20-60 seconds)
- **Devices Per Call**: How many devices to fetch at once (usually 50-200)

### Intervals
- **Discovery**: How often to scan for new devices (usually 60 minutes)
- **Polling**: How often to check device status (usually 5 minutes = 300 seconds)
- **Health Check**: How often to verify API is working (usually 5 minutes = 300 seconds)

---

## ❓ FAQ

**Q: Can I have different settings for different customers?**
A: Yes! Use **Organization** scope to set per-customer configs.

**Q: Can I have different settings for different office locations?**
A: Yes! Use **Site** scope to set per-location configs.

**Q: Can I have different settings per device brand?**
A: Yes! Use **Manufacturer** scope to set per-brand configs.

**Q: What if I set conflicting values at different scopes?**
A: The **most specific scope** wins. So Manufacturer > Site > Organization > Global

**Q: How do I know what value to use?**
A: See the "What Values Should I Set?" section above.

**Q: Changes aren't taking effect**
A: Wait 5 minutes for cache refresh, or contact your developer.

**Q: Can non-admins change settings?**
A: No, only Django admins can access the settings interface.

---

## 🔗 Need Help?

- **Admin User Guide**: See SETTINGS_MANAGEMENT.md
- **Developer Documentation**: See SETTINGS_INTEGRATION.md
- **Examples & Tests**: See tests/test_settings.py
- **System Technical**: See SETTINGS_SYSTEM_SUMMARY.md

---

**Last Updated**: January 28, 2026
**System**: django-micboard Settings Management v1.0
