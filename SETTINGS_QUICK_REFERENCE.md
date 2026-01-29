# Settings System - Quick Reference Card

## 🚀 Quick Start (Copy & Bookmark This)

### Access Settings
```
1. Go to: http://your-domain/admin/
2. Look for: "Micboard" section
3. Click: "Settings" or "Setting Definitions"
```

---

## 📋 Most Common Tasks

### Task 1: Set Battery Thresholds for Shure
```
Admin → Micboard → Settings → Add Setting
├─ Definition: "Battery Good Level (%)" → Value: 90
├─ Definition: "Battery Low Level (%)" → Value: 22
└─ Definition: "Battery Critical Level (%)" → Value: 5
Scope: Manufacturer → Shure → Save
```

### Task 2: Set Polling Interval for Organization
```
Admin → Micboard → Settings → Add Setting
├─ Definition: "Polling Interval (seconds)"
├─ Scope: Organization → [Your Company]
└─ Value: 300
→ Save
```

### Task 3: Quick Setup for New Manufacturer
```
Admin → Settings → Bulk Configuration
├─ Scope: Manufacturer
├─ Select: [Your Manufacturer]
├─ Fill in values (or leave blank to skip)
└─ Save
```

---

## 🎯 Common Values

### Battery Levels (per manufacturer)
| Level | Typical | Range |
|-------|---------|-------|
| Good | 90% | 80-95% |
| Low | 22% | 15-30% |
| Critical | 5% | 0-10% |

### API Configuration
| Setting | Typical | Min-Max |
|---------|---------|---------|
| Timeout | 30 sec | 5-60s |
| Max/Call | 100 | 10-500 |

### Polling
| Setting | Typical | Min-Max |
|---------|---------|---------|
| Interval | 300 sec | 10-3600s |
| Batch | 50 | 10-500 |

---

## ⚙️ Setting Types

| Type | Enter As | Examples |
|------|----------|----------|
| Number | `42` | `300`, `90` |
| Yes/No | `true` or `false` | `true`, `false` |
| Text | `"text"` | `"my-value"` |
| JSON | `{...}` | `{"key":"val"}` |

---

## 🔍 Scope Hierarchy

When looking up a setting, it checks in this order:

```
1. Manufacturer
2. Site
3. Organization
4. Global
5. Default
```

**First match wins** ← Use this

---

## 🆘 Troubleshooting

| Problem | What To Do |
|---------|-----------|
| Setting shows wrong value | Check scope (org/site/mfg) |
| Changes don't take effect | Wait 5 min (cache expires) |
| Can't find setting def | Go to "Setting Definitions" → Search |
| Form rejects my value | Check data type (number vs text) |
| Can't save setting | Check required fields filled |

---

## 💡 Tips

✅ **Use Bulk Configuration** for fast setup of many settings
✅ **Search by setting name** in Settings admin
✅ **Click setting name** to see what it does
✅ **Use scope filters** to see only relevant settings
✅ **Check the description** before entering value

---

## 🚫 Common Mistakes

❌ DON'T put text in a number field → Use "300" not "3 seconds"
❌ DON'T forget to select scope → Will save to wrong place
❌ DON'T expect instant changes → 5-min cache, or refresh admin
❌ DON'T use quotes in values → Enter `true`, not `"true"`

---

## 📞 Getting Help

- **Quick Questions?** See: SETTINGS_ADMIN_GUIDE.md
- **What does this setting do?** See: Setting Definition description
- **How do I integrate?** See: SETTINGS_INTEGRATION.md (developers)
- **System not working?** See: SETTINGS_MANAGEMENT.md

---

## 🎓 Understanding Scopes

### Manufacturer Scope
- **When**: Specific brand of devices (Shure, Sennheiser, etc.)
- **Example**: Shure battery threshold = 22%
- **Effect**: Only applies to that brand

### Organization Scope
- **When**: Your company (MSP or tenant)
- **Example**: Polling interval = 5 minutes
- **Effect**: All your devices, all brands

### Site Scope
- **When**: Office location (NYC, CA, etc.)
- **Example**: API timeout = 60 seconds (slow network)
- **Effect**: All devices at that location

### Global Scope
- **When**: System-wide default
- **Example**: Cache duration = 5 minutes
- **Effect**: Everything, everywhere

---

## 📊 Settings Provided

**Battery** (Manufacturer)
- battery_good_level
- battery_low_level
- battery_critical_level

**API** (Manufacturer)
- api_timeout
- device_max_requests_per_call
- health_check_interval

**Features** (Manufacturer)
- supports_discovery_ips
- supports_health_check

**Organization**
- discovery_enabled
- polling_enabled
- polling_interval_seconds
- polling_batch_size
- log_api_calls

**Global**
- cache_device_specs_minutes
- cache_settings_minutes

---

## ✅ Setup Checklist (First Time Admin)

- [ ] Access `/admin/` in browser
- [ ] Find "Micboard" section
- [ ] Click "Settings Definitions" (should see 17 items)
- [ ] Click "Settings" (should be mostly empty)
- [ ] Click "+ Add" next to Settings
- [ ] Try adding a test setting and save
- [ ] See success message ✓

**Done!** You're ready to configure.

---

## 🔄 Change Management

| Change | Time to Take Effect |
|--------|-------------------|
| Via admin UI | Instant |
| Via bulk form | Instant |
| After cache expires | 5 minutes max |

**Note**: System caches settings for 5 minutes for speed. Changes via admin UI are instant, but programmatic users may need to wait 5 minutes.

---

## 📱 Mobile Friendly?

❌ **Not optimized** for mobile
✅ **Works fine** on tablet
✅ **Best on** desktop (admin interface)

For mobile: Use laptop/desktop for admin tasks.

---

## 🔐 Permissions

✅ **Only Django admins** can access settings
✅ **Standard Django permissions** apply
✅ **No special group** setup needed
✅ Contact your system admin to add users to admin group

---

## 📌 Pinned References

**Most Used Setting**: `polling_interval_seconds`
- **Where**: Organization scope
- **Purpose**: How often to check device status
- **Default**: 300 seconds (5 minutes)
- **Range**: 10-3600 seconds

**Most Critical Setting**: `battery_low_level`
- **Where**: Manufacturer scope
- **Purpose**: Alert threshold for low battery
- **Default**: 20-25% (varies by brand)
- **Impact**: Affects all device health alerts

---

## 🎯 One-Liner Links

| What | Where |
|------|-------|
| Add new setting | `/admin/micboard/setting/add/` |
| View all settings | `/admin/micboard/setting/` |
| Configure manufacturer | `/admin/settings/manufacturer/` |
| Settings overview | `/admin/settings/` |
| Bulk configure | `/admin/settings/bulk/` |

---

**Version**: 1.0
**Last Updated**: January 28, 2026
**Print This**: Yes, keep on desk
**Update Frequency**: Rarely (only when new settings added)
