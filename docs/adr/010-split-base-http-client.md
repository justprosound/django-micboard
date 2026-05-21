# ADR-010: Split base_http_client.py into Three Concerns

**Status:** Proposed
**Date:** 2026-05-21
**Deciders:** (to be assigned)

## Context

`integrations/base_http_client.py` is 635 lines — the third-largest file in the project and the largest file outside `models/` and `admin/`. It mixes three distinct concerns in a single class hierarchy:

| Concern | Approx. Lines | What It Contains |
|---------|--------------|------------------|
| **HTTP Transport** | ~250 | Connection pooling (`requests.Session` + `HTTPAdapter` + `urllib3.Retry`), TLS verification, auth configuration template method, request dispatch |
| **Polling Orchestration** | ~200 | `BasePollingMixin` — coordination logic for when to poll, how to sequence requests, response aggregation |
| **Health Tracking** | ~100 | Health recording methods, status computation, health metadata |

The class diagram is:

```
BaseHTTPClient (HTTP transport + health tracking)
     └── with BasePollingMixin (mixed in via cooperative inheritance)
            ├── ShureSystemAPIClient
            └── SennheiserSystemAPIClient
```

Additionally, the file lives at `integrations/` root rather than in `integrations/common/`, which is inconsistent with the rest of the shared integration infrastructure (`common/base.py`, `common/rate_limiter.py`, etc.).

This structure causes:
- **Single-file coupling.** Understanding the polling logic requires reading through HTTP transport code. A change to transport retry can accidentally break health tracking.
- **No isolated testing.** Currently the only way to test polling orchestration is through a full HTTP client (slow, requires network mocking).
- **Inconsistent location.** Every other shared infrastructure file lives in `integrations/common/`, making `base_http_client.py` an outlier.

## Decision

1. **Split into three modules behind the same composite class** so no external caller code changes:

   ```
   integrations/
     common/
       http_transport.py    (~250L) — Connection pooling, retry, auth configuration.
                                      Pure transport — knows nothing about polling or health.
       health_tracker.py     (~100L) — Health recording, status computation, metadata.
                                      Pure state — depends only on timestamp/boolean inputs.
     services/shared/
       polling_orchestrator.py (~200L) — Coordination logic: when to poll, sequencing, aggregation.
                                         Depends on transport seam (injectable), not on HTTP directly.
   ```

2. **`BaseHTTPClient` becomes a thin composition class** that instantiates and delegates to all three. The end-user class signature and method set remain identical — no call-site changes.

3. **Move to `integrations/common/`**. The new modules live in `integrations/common/` for consistency. The old `base_http_client.py` becomes a re-export shim for one release cycle, then is removed.

4. **Each concern defines its own test seam:**
   - `http_transport.py` tests: connection pooling configuration, retry behavior (mock `requests.adapters.HTTPAdapter`), auth template method.
   - `health_tracker.py` tests: pure computation — feed timestamps, assert health status. No mocks needed.
   - `polling_orchestrator.py` tests: inject fake transport, verify polling sequence. No network required.

## Consequences

- **Positive:** Each concern independently testable. Polling orchestration becomes a pure coordination module with a small seam — inject a fake transport to test any polling sequence. Health tracking is stateless computation. HTTP transport tests stay in the transport module.
- **Negative:** Three files instead of one. The composition class adds ~20 lines of boilerplate.
- **Migration:** (a) Extract `http_transport.py`, (b) extract `health_tracker.py`, (c) extract `polling_orchestrator.py`, (d) rewrite `BaseHTTPClient` as composition, (e) move to `integrations/common/`, (f) leave re-export shim, (g) remove shim after one release cycle. Execute as a single PR — no caller changes needed.

## Compliance

- No new file in `integrations/` root should exceed 200 lines. All shared infrastructure goes in `integrations/common/`.
- CI will flag any class in `http_transport.py` that imports from a polling or health module (enforce dependency direction).
