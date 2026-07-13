# ADR-004: Standardize Manufacturer Plugin System

**Status:** Proposed
**Date:** 2026-05-20
**Updated:** 2026-05-21
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

Shure has 8 files totaling ~1,153 lines; Sennheiser has 7 files totaling ~772 lines. The two stacks are structurally identical — only the API protocol details differ (Shure uses REST + WebSocket; Sennheiser uses REST + SSE). File-level duplication is ~80-90% by structural similarity.

A shared base framework exists but is undersized:

| Base File | Lines | Role | Gaps |
|-----------|-------|------|------|
| `services/common/base/client.py` | Shared `httpx.Client` transport, typed retries, and health tracking | Manufacturer clients compose device and discovery sub-clients instead of delegating their APIs |
| `services/common/base/plugin.py` | `BasePlugin`, the typed `ManufacturerPlugin` contract, and plugin lookup | Discovery and device workflows depend on this boundary |
| `services/common/base/resilience.py` | Shared connection pooling and bounded connection retries | HTTP status retries stay in the calling service where replay safety is known |
| `services/common/base/rate_limiter.py` | Rate limiting decorators | Applied by integration sub-clients |

The per-manufacturer duplication patterns include:
- Retry configuration duplicated in each `client.py`
- Rate-limit application (same decorators re-exported in each `rate_limiter.py`)
- Exception wrapping (same mapping from HTTP errors to domain exceptions)
- Device model mapping (similar `_map_device_type()` in each `transformers.py`)

## Decision

1. **Extract a shared plugin framework** into `micboard/integrations/common/`:
   - `http_client.py` — shared HTTP client with retry, rate limiting, TLS verify. Extracted from the transport concern in `base_http_client.py`.
   - `base_plugin.py` — concrete base plugin with lifecycle hooks, sync methods, and default streaming setup
   - `base_discovery_client.py` — shared discovery probe logic (HTTP ping, port scan patterns)
   - `base_transformers.py` — shared field-mapping helpers (model type inference, runtime formatting)
2. **Shure and Sennheiser plugins inherit from the shared base classes**, overriding only their protocol-specific differences (URL structure, auth headers, response parsing, streaming type).
3. **Each manufacturer plugin's total LOC should decrease by ~40-60%** after adopting shared bases (Shure: ~1,153 → ~460-690; Sennheiser: ~772 → ~300-460).
4. **The `PluginRegistry`** at `services/manufacturer/plugin_registry.py` stays as the discovery mechanism.
5. **`integrations/base_http_client.py`** is a parallel concern — its split into three modules (transport, polling, health) is tracked by a separate ADR (see ADR-010).

## Consequences

- **Positive:** Adding a new manufacturer (e.g., Wisycom) requires writing only the protocol-specific layer (~200-300 lines instead of ~800-1,000). Bug fixes to retry, timeout, or logging logic propagate to all plugins at once. The existing `base_http_client.py` (635L) is not a prerequisite — plugin refactoring can proceed independently of the HTTP client split.
- **Negative:** Protocol divergence is harder to accommodate if a manufacturer has fundamentally different semantics (e.g., gRPC instead of REST). Mitigate by keeping base classes overridable at the method level.
- **Migration:** Refactor in one PR per plugin (Shure first as the larger codebase), then remove duplication in a final cleanup.

## Compliance

- New manufacturer plugins must be reviewed to ensure no copy-paste from existing stacks.
- CI must check that `integrations/<manufacturer>/` files do not exceed a threshold of structural similarity with existing plugins.
