# ADR-004: Standardize Manufacturer Plugin System

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

Manufacturer integrations live in `micboard/integrations/<manufacturer>/`. Shure and Sennheiser each have:

- `plugin.py` — plugin class definition
- `client.py` — HTTP API client
- `device_client.py` — per-device API client
- `discovery_client.py` — network discovery client
- `transformers.py` — data transformation/mapping
- `exceptions.py` — custom exceptions
- `rate_limiter.py` — rate limiting

Shure has 8 files totaling ~1,153 lines; Sennheiser has 7 files totaling ~772 lines. The two stacks are structurally identical — only the API protocol details differ (Shure uses REST + WebSocket; Sennheiser uses REST + SSE). The file-level duplication is ~80-90%.

A base plugin architecture exists in `micboard/manufacturers/base.py` (98 lines) but provides only abstract stubs. The real shared patterns (rate limiting, request retry, pagination, error classification, device mapping) are copy-pasted with minor tweaks across each manufacturer.

## Decision

1. **Extract a shared plugin framework** into `micboard/integrations/common/`:
   - `http_client.py` — shared HTTP client with retry, rate limiting, TLS verify
   - `base_plugin.py` — concrete base plugin with lifecycle hooks, sync methods
   - `base_discovery_client.py` — shared discovery probe logic
   - `base_transformers.py` — shared field-mapping helpers
   - `exceptions.py` — shared exception taxonomy
2. **Shure and Sennheiser plugins inherit from the shared base classes**, overriding only their protocol-specific differences (URL structure, auth headers, response parsing, streaming type).
3. **Each manufacturer plugin's total LOC should decrease by ~40-60%** after adopting shared bases.
4. **The `PluginRegistry`** at `services/manufacturer/plugin_registry.py` stays as the discovery mechanism.

## Consequences

- **Positive:** Adding a new manufacturer (e.g., Wisycom) requires writing only the protocol-specific layer (~200-300 lines instead of ~800-1,000). Bug fixes to retry, timeout, or logging logic propagate to all plugins at once.
- **Negative:** Protocol divergence is harder to accommodate if a manufacturer has fundamentally different semantics (e.g., gRPC instead of REST). Mitigate by keeping base classes overridable at the method level.
- **Migration:** Refactor in one PR per plugin (Shure first as the larger codebase), then remove duplication in a final cleanup.

## Compliance

- New manufacturer plugins must be reviewed to ensure no copy-paste from existing stacks.
- CI must check that `integrations/<manufacturer>/` files do not exceed a threshold of structural similarity.
