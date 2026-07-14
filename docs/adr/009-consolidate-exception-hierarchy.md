# ADR-009: Consolidate Exception Hierarchy

**Status:** Proposed
**Date:** 2026-05-21
**Deciders:** (to be assigned)

## Context

django-micboard has three exception files across three layers, each defining its own sub-hierarchy:

| File | Lines | Content |
|------|-------|---------|
| `micboard/exceptions.py` | 161 | Root hierarchy: `MicboardError(Exception)` → 6 subclasses (`ManufacturerNotSupportedError`, `HardwareNotFoundError`, `HardwareValidationError`, `APIError`, `LocationNotFoundError`, `ServiceError`). Each includes `message`, `code`, `details`. |
| `services/shared/exceptions.py` | 39 | Historical re-export facade over root exceptions, plus two new placeholders: `DiscoveryError`, `LocationAlreadyExistsError`. |
| `integrations/common/exceptions.py` | 71 | Integration-layer: `APIError`, `APIRateLimitError`, `APIAuthenticationError`, `APITimeoutError`. |

Additionally, each manufacturer plugin has its own 25-line `exceptions.py` inheriting from the integration common ones (`ShureAPIError(APIError)`, `SennheiserAPIError(APIError)`).

This architecture causes three problems:

1. **Shadowed built-in.** `services/shared/exceptions.py` exports `ConnectionError = APIError`, shadowing Python's built-in `ConnectionError`. Any code importing from this module silently replaces the standard exception. A `try/except ConnectionError` may behave differently depending on import order.

2. **Ambiguous catch boundaries.** A top-level handler must know which module's exceptions to catch. The re-export layer adds no behaviour — only aliases — so it creates confusion without benefit.

3. **Stale separation.** The three-file split pretends the layers are independent, but `services/shared/exceptions.py` re-exports from the root, and `integrations/common/exceptions.py` defines types that could be in the root hierarchy. The split adds navigation cost without clarity.

## Decision

1. **Collapse into one authoritative hierarchy** in `micboard/exceptions.py`:
   - Move `APIRateLimitError`, `APIAuthenticationError`, `APITimeoutError` from `integrations/common/exceptions.py` into the root hierarchy as `MicboardError` subclasses (with `code` values like `"API_RATE_LIMIT"`, `"API_AUTH_ERROR"`, `"API_TIMEOUT"`).
   - Keep manufacturer-specific exceptions (`ShureAPIError`, `ShureAPIRateLimitError`) in their respective `exceptions.py` files — they inherit from the root but live at the seam where they're raised.
   - Remove `services/shared/exceptions.py` entirely. Its aliases add no value; its two unique exceptions (`DiscoveryError`, `LocationAlreadyExistsError`) move to the root file.

2. **Eliminate the `ConnectionError` alias.** Rename to `APIConnectionError` or remove entirely (`APIError` already covers the case).

3. **Standardise on `code` for programmatic handling.** All exceptions use the existing pattern: `MicboardError` subclasses carry a `code` string (e.g., `"HARDWARE_NOT_FOUND"`) and a `details` dict. Code should catch `MicboardError` and switch on `code`, not on exception type.

4. **Remove the re-export layer.** Update all call sites that import from `services/shared/exceptions` to import from `micboard.exceptions` instead.

## Final Hierarchy

```
Exception
  └── MicboardError (message: str, code: str, details: dict)
        ├── ManufacturerNotSupportedError    code="MANUFACTURER_NOT_SUPPORTED"
        ├── HardwareNotFoundError            code="HARDWARE_NOT_FOUND"
        ├── HardwareValidationError          code="HARDWARE_VALIDATION"
        ├── APIError                         code="API_ERROR"
        │     ├── APIRateLimitError          code="API_RATE_LIMIT"
        │     ├── APIAuthenticationError     code="API_AUTH_ERROR"
        │     └── APITimeoutError            code="API_TIMEOUT"
        ├── LocationNotFoundError            code="LOCATION_NOT_FOUND"
        ├── LocationAlreadyExistsError       code="LOCATION_ALREADY_EXISTS"
        ├── DiscoveryError                   code="DISCOVERY_ERROR"
        └── ServiceError                     code="SERVICE_ERROR"
```

## Consequences

- **Positive:** One module to import, one hierarchy to learn. No builtin shadowing. Programmatic handling uses `code` strings consistently. Stale re-export layer removed (~39 lines + cognitive load).
- **Negative:** ~15-25 import sites need updating from `services/shared/exceptions` to `micboard.exceptions`. Manufacturer plugin exception files need their imports adjusted.
- **Migration:** Single PR. (a) Consolidate root hierarchy, (b) update `integrations/common/exceptions.py` to inherit from root, (c) remove `services/shared/exceptions.py`, (d) update all import sites.

## Compliance

- CI will reject any `except ConnectionError` that isn't explicitly catching the built-in (lint rule for `from micboard.exceptions import ...`).
- No new exception modules outside `micboard/exceptions.py` or plugin-local `exceptions.py` files.
