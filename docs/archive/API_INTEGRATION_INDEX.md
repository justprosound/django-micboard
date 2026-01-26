# API Integration Documentation Index

**Version:** 26.01.22
**Last Updated:** January 22, 2026
**Status:** ✅ Complete & Current

## Quick Navigation

### For Shure Integration
1. **Start Here:** [Shure Integration Guide](./shure-integration.md)
   - Authentication, configuration, and setup
   - API endpoints and WebSocket reference
   - Troubleshooting and best practices

2. **Quick Reference:** [Integration References](./integration-references.md) → Shure Section
   - Configuration templates
   - Import statements
   - Common errors and solutions

3. **Troubleshooting:** [Shure Troubleshooting Guide](./SHURE_TROUBLESHOOTING.md)
   - Detailed diagnostic procedures
   - Common issues and resolutions

4. **Testing:** [Shure Test Suite](./SHURE_TEST_SUITE_COMPLETION.md)
   - Test coverage overview (30 tests, 100% passing)
   - Test architecture and patterns

### For Sennheiser Integration
1. **Start Here:** [Sennheiser Integration Guide](./sennheiser-integration.md)
   - Device configuration and setup
   - Authentication and credentials
   - API specifications and endpoints

2. **Critical Setup Info:**
   - ⚠️ Devices cannot be accessed in factory default state
   - Step-by-step process to enable third-party API access
   - HTTP Basic Auth (username: `api`, password via Control Cockpit)

3. **Quick Reference:** [Integration References](./integration-references.md) → Sennheiser Section
   - Configuration templates
   - API specification downloads
   - Troubleshooting table

### For General Integration Work
1. **Architecture Overview:** [Architecture](./architecture.md)
   - System design and data flow
   - Component relationships
   - Plugin architecture

2. **Plugin Development:** [Plugin Development Guide](./plugin-development.md)
   - How to add new manufacturers
   - Interface requirements
   - Testing patterns

3. **Rate Limiting:** [Rate Limiting](./rate-limiting.md)
   - Shared rate limiter implementation
   - Configuration and usage

---

## API Reference Links

### Sennheiser Official Specifications
- 📄 **TCCM API 1.8 JSON Specification**
  https://www.sennheiser.com/globalassets/digizuite/51646-en-tccm-api-1_8.json

- 📄 **TC Bar OpenAPI 3.0 YAML (1.12 Release)**
  https://www.sennheiser.com/globalassets/digizuite/52626-en-tc-bar-openapi-3rd-party-release-1.12.yaml

- 📖 **Sound Control Protocol Documentation**
  https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html

- 📖 **Sound Control Protocol v2 (Draft 0.1)**
  https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/resources/Sennheiser%20Sound%20Control%20Protocol%20v2_draft_0.1.html

### Shure Official Documentation
- 🔗 **Shure System API**
  https://www.shure.com/en-US/products/software/systemapi

- 🔗 **Shure API Explorer**
  https://shure.secure.force.com/apiexplorer

- 🔗 **Shure Developer Portal**
  https://developer.shure.com

---

## Documentation Files

| File | Purpose | Size | Status |
|------|---------|------|--------|
| [shure-integration.md](./shure-integration.md) | Comprehensive Shure guide | 11 KB | ✅ Complete |
| [sennheiser-integration.md](./sennheiser-integration.md) | Comprehensive Sennheiser guide | 9.7 KB | ✅ Complete |
| [integration-references.md](./integration-references.md) | Quick reference & API index | 11 KB | ✅ Complete |
| [architecture.md](./architecture.md) | System architecture (updated) | - | ✅ Updated |
| [plugin-development.md](./plugin-development.md) | Plugin development guide | - | ✅ Available |
| [rate-limiting.md](./rate-limiting.md) | Rate limiting reference | - | ✅ Available |
| [SHURE_TROUBLESHOOTING.md](./SHURE_TROUBLESHOOTING.md) | Shure troubleshooting | - | ✅ Available |
| [SHURE_TEST_SUITE_COMPLETION.md](./SHURE_TEST_SUITE_COMPLETION.md) | Test documentation | - | ✅ Available |
| [DOCUMENTATION_UPDATE_SUMMARY.md](./DOCUMENTATION_UPDATE_SUMMARY.md) | Update summary | 8.9 KB | ✅ Complete |

---

## Key Configuration Information

### Sennheiser Setup

**Factory Default State:**
```
⚠️ Sennheiser devices CANNOT be accessed via API in factory default state
```

**Enable Third-Party API Access:**
1. Connect device to Sennheiser Control Cockpit
2. Navigate to device page/settings
3. Enable third-party access option
4. Configure strong third-party password

**Authentication:**
```
Method: HTTP Basic Authentication (RFC 7617)
Username: api (fixed)
Password: Your configured third-party password
Required: With every request
```

### Shure Setup

**Authentication:**
```
Method: HTTP Digest Authentication (RFC 7616)
Shared Key: Configured at system level
Base URL: https://<ip>:2420
WebSocket: wss://<ip>:2420/api/v1/ws
```

**Configuration:**
- Enable Shure System API on device
- Configure static IP or DHCP reservation
- Set up proper network connectivity
- Configure firewall rules if needed

---

## Common Tasks

### I need to configure Sennheiser
→ Start with [Sennheiser Integration Guide](./sennheiser-integration.md)
- Section: "Device Configuration"
- Section: "Authentication"
- Section: "Configuration in Django Settings"

### I need to configure Shure
→ Start with [Shure Integration Guide](./shure-integration.md)
- Section: "Device Configuration"
- Section: "Authentication"
- Section: "Configuration in Django Settings"

### I need to add a new manufacturer
→ Start with [Plugin Development Guide](./plugin-development.md)
- Then reference [Integration References](./integration-references.md) for patterns
- Use [Shure Integration Guide](./shure-integration.md) as implementation example

### I'm getting API errors
→ Check manufacturer-specific troubleshooting:
- Shure: [Shure Troubleshooting Guide](./SHURE_TROUBLESHOOTING.md)
- Sennheiser: [Sennheiser Integration Guide](./sennheiser-integration.md) → Troubleshooting section
- General: [Integration References](./integration-references.md) → Troubleshooting Reference section

### I need to understand the architecture
→ Start with [Architecture Overview](./architecture.md)
- Then read [Integration References](./integration-references.md) → "Plugin Architecture"
- Reference specific guides as needed

### I need rate limiting information
→ See [Rate Limiting Documentation](./rate-limiting.md)
- Or check Integration References for manufacturer-specific limits

---

## Search by Topic

### Authentication Methods
- **Sennheiser:** HTTP Basic Auth
  → [Sennheiser Integration](./sennheiser-integration.md#authentication)
- **Shure:** HTTP Digest Auth
  → [Shure Integration](./shure-integration.md#authentication)

### Device Setup & Configuration
- **Sennheiser:** Control Cockpit required, third-party access must be enabled
  → [Sennheiser Integration](./sennheiser-integration.md#device-configuration)
- **Shure:** System API must be enabled
  → [Shure Integration](./shure-integration.md#device-configuration)

### Rate Limiting
- **Sennheiser:** Per-device limits (see specs)
  → [Sennheiser Integration](./sennheiser-integration.md#rate-limiting)
- **Shure:** 10 req/s default, 20 req burst
  → [Shure Integration](./shure-integration.md#rate-limiting)

### Error Handling & Troubleshooting
- **Shure Specific:** [SHURE_TROUBLESHOOTING.md](./SHURE_TROUBLESHOOTING.md)
- **Both Manufacturers:** [Integration References](./integration-references.md#troubleshooting-reference)
- **Sennheiser:** [Sennheiser Integration](./sennheiser-integration.md#troubleshooting)

### Security Best Practices
- **Both:** [Integration References](./integration-references.md#security-best-practices)
- **Shure:** [Shure Integration](./shure-integration.md#best-practices)
- **Sennheiser:** [Sennheiser Integration](./sennheiser-integration.md#best-practices)

### Performance Optimization
- **Both:** [Integration References](./integration-references.md#performance-considerations)
- **Shure:** [Shure Integration](./shure-integration.md#best-practices)
- **Sennheiser:** [Sennheiser Integration](./sennheiser-integration.md#best-practices)

---

## Integration Status

| Manufacturer | Status | Test Coverage | API Docs | Config Guide | Troubleshooting |
|--------------|--------|---------------|----------|--------------|-----------------|
| Shure | ✅ Production Ready | 30 tests (100%) | ✅ Complete | ✅ Complete | ✅ Complete |
| Sennheiser | ✅ Integration Ready | Configurable | ✅ Complete | ✅ Complete | ✅ Complete |

---

## Code Examples

### Import Common Utilities
```python
from micboard.integrations.common import rate_limit, APIError, APIRateLimitError
```

### Import Manufacturer Clients
```python
# Shure
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.exceptions import ShureAPIError, ShureAPIRateLimitError

# Sennheiser
from micboard.integrations.sennheiser.client import SennheiserAPIClient
from micboard.integrations.sennheiser.exceptions import SennheiserAPIError, SennheiserAPIRateLimitError
```

### Use Manufacturer Plugin
```python
from micboard.manufacturers import get_manufacturer_plugin

plugin = get_manufacturer_plugin("shure")  # or "sennheiser"
devices = plugin.get_devices()
```

---

## Development Workflow

1. **Understand the Architecture**
   - Read [Architecture Overview](./architecture.md)

2. **Choose Your Manufacturer**
   - Shure: [Shure Integration Guide](./shure-integration.md)
   - Sennheiser: [Sennheiser Integration Guide](./sennheiser-integration.md)

3. **Configure Your Environment**
   - Follow Django Settings Configuration section in chosen guide
   - Set environment variables

4. **Implement Your Feature**
   - Reference [Plugin Development Guide](./plugin-development.md)
   - Use [Integration References](./integration-references.md) for import patterns

5. **Test Your Implementation**
   - Add tests following patterns from [SHURE_TEST_SUITE_COMPLETION.md](./SHURE_TEST_SUITE_COMPLETION.md)
   - Run test suite to verify

6. **Troubleshoot Issues**
   - Check manufacturer-specific troubleshooting guide
   - Reference [Integration References](./integration-references.md) for common issues

---

## Support & References

### Primary Documentation
- Architecture: [architecture.md](./architecture.md)
- Shure: [shure-integration.md](./shure-integration.md)
- Sennheiser: [sennheiser-integration.md](./sennheiser-integration.md)

### Quick Reference
- API Index: [integration-references.md](./integration-references.md)
- Plugin Development: [plugin-development.md](./plugin-development.md)
- Rate Limiting: [rate-limiting.md](./rate-limiting.md)

### Troubleshooting
- Shure: [SHURE_TROUBLESHOOTING.md](./SHURE_TROUBLESHOOTING.md)
- General: [integration-references.md](./integration-references.md#troubleshooting-reference)

### Testing
- Test Documentation: [SHURE_TEST_SUITE_COMPLETION.md](./SHURE_TEST_SUITE_COMPLETION.md)

### Updates & Status
- Documentation Summary: [DOCUMENTATION_UPDATE_SUMMARY.md](./DOCUMENTATION_UPDATE_SUMMARY.md)
- Phase Status: [PHASE_2.1_CONSOLIDATION_COMPLETE.md](./PHASE_2.1_CONSOLIDATION_COMPLETE.md)

---

**Last Updated:** January 22, 2026
**Version:** CalVer 26.01.22
**Status:** ✅ Current & Complete
**Maintainer:** Django Micboard Development Team
