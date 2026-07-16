# ADR-010: Split base_http_client.py into Three Concerns

**Status:** Superseded — plan abandoned in favor of composite client pattern
**Date:** 2026-05-21
**Deciders:** (to be assigned)

This ADR documents a plan that was **NOT implemented**. The three-module split described below was abandoned in favor of a composite client pattern that achieved the same goals (separation of transport bounds, circuit breaking, health checking) without breaking vendor client API compatibility.

## Context (Historical)

`integrations/base_http_client.py` was 635 lines — the third-largest file in the project and the largest file outside `models/` and `admin/`. It mixed three distinct concerns in a single class hierarchy:

| Concern | Approx. Lines | What It Contains |
|---------|--------------|------------------|
| **HTTP Transport** | ~250 | Connection pooling (`httpx.Client`), TLS verification, auth configuration template method, request dispatch, and typed retries |
| **Polling Orchestration** | ~200 | Former polling mixin coordinating request sequencing and response aggregation |
| **Health Tracking** | ~100 | Health recording methods, status computation, health metadata |

The class diagram was:
```
BaseHTTPClient (HTTP transport + health tracking)
      └── former polling mixin (mixed in via cooperative inheritance)
             ├── ShureSystemAPIClient
             └── SennheiserSystemAPIClient
```

Additionally, the file lived at `integrations/` root rather than in `integrations/common/`, which is inconsistent with the rest of the shared integration infrastructure (`common/base.py`, `common/rate_limiter.py`, etc.).

## Actual Implemented Architecture (Superseding This ADR)

Instead of the three-module split, the team adopted a **composite client pattern** in `micboard/services/common/base/client.py` (392 lines):

- `BaseHTTPClient` composes:
  - `BoundedHTTPTransport` (streaming response size enforcement)
  - `CircuitBreaker` (failure threshold + recovery timeout)
  - `HealthCheckMixin` (health check endpoint probing)

- Vendor clients (`ShureSystemAPIClient`, `SennheiserSystemAPIClient`) **inherit** from this composite `BaseHTTPClient` and implement abstract methods for auth, endpoints, and exception classes

- Sub-clients for discovery/devices are **composed on the vendor client** (e.g., `ShureDiscoveryClient`, `ShureDeviceClient`)

This achieves the same goals (transport bounds, circuit breaking, health checking) without the three-module extraction that would have required breaking vendor client public APIs.

## Original Plan (Abandoned)

The original decision was to split into three modules behind the same composite class:

```
integrations/
  common/
    http_transport.py    (~250L) — Connection pooling, retry, auth configuration.
    health_tracker.py     (~100L) — Health recording, status computation, metadata.
  services/shared/
    polling_orchestrator.py (~200L) — Coordination logic: when to poll, sequencing, aggregation.
```

`BaseHTTPClient` becomes a thin composition class (~20 lines boilerplate) instantiating and delegating to all three. Call sites move directly to the new domain modules in the same change. Move shared behavior directly into canonical domain modules. No re-export shim or compatibility module retained.

Each concern defines its own test seam:
- `http_transport.py` tests: connection pooling configuration, retry behavior with `httpx.MockTransport`, and the auth template method.
- `health_tracker.py` tests: pure computation — feed timestamps, assert health status. No mocks needed.
- `polling_orchestrator.py` tests: inject fake transport, verify polling sequence. No network required.

## Why the Plan Was Abandoned

The cooperative multiple inheritance used by the original `BaseHTTPClient` (with vendor clients as subclasses) could not be cleanly decomposed into three separate modules without:
1. Breaking vendor client API compatibility (would require all callers to update)
2. Circular import risk with `polling_orchestrator` depending on transport seam
3. Loss of method resolution order for callers that overrode specific mixin methods

The composite pattern achieved the same architectural goals (bounded transport, circuit breaker, health mixin as separate concerns) while preserving the inheritance-based vendor client API.

## References

- See ADR-004 for manufacturer plugin architecture using this composite client
- Current implementation: `micboard/services/common/base/client.py`
