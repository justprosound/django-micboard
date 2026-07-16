<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Split Base HTTP Client (Superseded — Plan Abandoned)

## Project Description

`integrations/base_http_client.py` was 635 lines — the third-largest file in the project and the largest file outside `models/` and `admin/`. It mixed three distinct concerns in a single class hierarchy:

| Concern | Approx. Lines | What It Contains |
|---------|--------------|------------------|
| **HTTP Transport** | ~250 | Connection pooling (`httpx.Client`), TLS verification, auth configuration template method, request dispatch, typed retries |
| **Polling Orchestration** | ~200 | Former polling mixin coordinating request sequencing and response aggregation |
| **Health Tracking** | ~100 | Health recording methods, status computation, health metadata |

The class diagram was:
```
BaseHTTPClient (HTTP transport + health tracking)
      └── former polling mixin (mixed in via cooperative inheritance)
             ├── ShureSystemAPIClient
             └── SennheiserSystemAPIClient
```

Additionally, the file lived at `integrations/` root rather than in `integrations/common/`, inconsistent with the rest of the shared integration infrastructure (`common/base.py`, `common/rate_limiter.py`, etc.).

## Project Status: Superseded / Plan Abandoned

**This plan was NOT implemented.** During implementation planning, the team determined that the cooperative inheritance model used by the existing `BaseHTTPClient` (with vendor clients `ShureSystemAPIClient` and `SennheiserSystemAPIClient` as subclasses) could not be cleanly decomposed into three separate modules without breaking vendor client API compatibility.

Instead, the **actual implemented architecture** kept a composite `BaseHTTPClient` in `micboard/services/common/base/client.py` (392 lines) that:
- Composes `BoundedHTTPTransport` (streaming response size enforcement)
- Composes `CircuitBreaker` (failure threshold + recovery timeout)
- Inherits `HealthCheckMixin` (health check endpoint probing)
- Defines abstract methods for vendor-specific auth, endpoints, exception classes

Vendor clients (`ShureSystemAPIClient`, `SennheiserSystemAPIClient`) inherit from this composite `BaseHTTPClient` and implement the abstract methods. Sub-clients (`ShureDiscoveryClient`, `ShureDeviceClient`, etc.) are composed on the vendor client.

This approach achieved the same goals (separation of transport bounds, circuit breaking, health checking) without the three-module split.

## Technical Uncertainties (Original Plan)

### Uncertainty #1: Preserving Cooperative Inheritance Semantics Across Composition Boundary

**Description:** The original `BaseHTTPClient` used cooperative multiple inheritance (`super().method()`) across transport, polling, and health mixins. Moving to composition requires explicit delegation while preserving method resolution order for callers that overrode specific methods.

**Experiments:**
- Attempted: keep `BaseHTTPClient` as subclass of all three, delegate via `super()` — circular import risk with `polling_orchestrator` depending on transport seam
- Adopted: `BaseHTTPClient` instantiates three components in `__init__`; exposes `.transport`, `.health`, `.polling` properties; overridden methods in vendor clients (`ShureSystemAPIClient`, `SennheiserSystemAPIClient`) updated to call `self.transport.request()` / `self.polling.run()` explicitly

**Results / Learnings / Success:**
- (Plan abandoned) — the team found the existing composite pattern with abstract vendor methods was more maintainable and didn't require breaking vendor client APIs

### Uncertainty #2: Dependency Direction Enforcement

**Description:** After split, `http_transport.py` must not import from polling or health modules. `polling_orchestrator.py` depends on transport seam (interface), not concrete HTTP. Need CI enforcement.

**Experiments:**
- Attempted: `import-linter` contract — complex config for this case
- Adopted: custom AST check in `tests/architecture/test_http_transport_isolation.py` — parses `http_transport.py`, asserts no imports from `polling_orchestrator` or `health_tracker`; runs in CI

**Results / Learnings / Success:**
- (Plan abandoned) — no such test file exists because the three-module split was never implemented

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Composition Design | ~20% | ADR-010, module boundaries, dependency direction |
| (engineer) | Transport / Health Implementation | ~30% | `http_transport.py`, `health_tracker.py`, vendor client updates |
| (engineer) | Polling Orchestrator / Tests | ~30% | `polling_orchestrator.py`, fake transport, CI enforcement |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-010 Split base_http_client.py into Three Concerns (Superseded)](../../adr/010-split-base-http-client.md)

**PRs:**
- (plan abandoned — no extraction PRs)