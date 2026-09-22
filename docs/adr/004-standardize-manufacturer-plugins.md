---
title: "ADR-004: Compose Manufacturer Plugins Around Shared Transport"
---
**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-09-22
**Deciders:** Project team

## Context

Manufacturer integrations use a common directory shape, but their protocols are not interchangeable.
Shure uses REST plus WebSocket; Sennheiser SSCv2 uses REST plus an HTTP Basic-authenticated SSE
stream whose same-origin `Content-Location` is configured over a separate connection. Discovery
resources, payloads, and transforms also differ by vendor.

Shared HTTPS validation, bounded response handling, retries, rate limits, circuit breaking, health
tracking, plugin lookup, and the canonical exception hierarchy already live under
`micboard/services/common/base/` and `micboard/exceptions.py`.

A broad discovery or transformer inheritance tree would make protocol differences implicit and
would have only two consumers. Similar filenames are not sufficient evidence for inheritance.

## Decision

1. Keep shared, verified transport and plugin contracts in `micboard/services/common/base/`; do
   not create a second common hierarchy under integrations.
2. Keep discovery, device endpoints, transforms, and streaming adapters manufacturer-local.
3. Extract only proven pure helpers used by at least two live integrations.
4. Keep `micboard.services.common.base.plugin` as the construction boundary — one
   `build_manufacturer_plugin(manufacturer)` front door that resolves the class once, caches it,
   and raises when no integration ships for the code — and manufacturer sync services as the
   persistence and orchestration boundary.
5. Contract-test each protocol against authoritative behavior, including authentication, bounded
   payloads, origin validation, and connection lifecycle.
6. Share the transport-neutral subscription lifecycle: `services/realtime/subscription_runner.py`
   owns leasing, eligible inventory selection, connection tracking, and activation rechecks, and
   `services/realtime/subscription_lifecycle_service.py` owns transform, persistence, chassis
   projection, and broadcast. Each integration declares its own `realtime_transport` and
   implements `subscribe_to_chassis`, keeping connection setup, authentication, event framing, and
   cleanup inside the integration package. No orchestration code names a vendor.
7. Keep vendor client APIs limited to operations used by the production plugin contract. Do not
   retain speculative enrichment endpoints or test-only forwarding methods.
8. There are two polling surfaces, and they are not duplicates.
   `ManufacturerSyncService` owns whole-manufacturer inventory synchronisation with its audit
   row and broadcast; `services/sync/polling_api.py` owns the managed-device path, polling one
   operator-registered chassis through its persisted `ManufacturerAPIServer` after an ownership
   check. Neither may grow the other's responsibility.
9. Outside `micboard/integrations/`, only the API-server connection surface
   (`services/integrations/api_server_service.py`) and the admin connection checker may name a
   vendor. Every other module obtains its integration through
   `build_manufacturer_plugin(manufacturer)`.

**Correction (2026-09-22):** clause 7 read as though only one polling module existed, while
`services/sync/polling_api.py` had been polling managed devices alongside the synchronization
service the whole time; clauses 8 and 9 record the boundary that actually holds. That module
also imported `ShurePlugin` directly and pointed its docstring at `polling_service.py`, which
no longer exists — it now builds through `build_manufacturer_plugin` like every other
outbound path.

## Consequences

- **Positive:** Shared safety fixes propagate while protocol behavior remains locally readable and
  independently testable.
- **Positive:** New integrations have one stable transport/plugin seam without inheriting unrelated
  discovery or streaming assumptions.
- **Negative:** Protocol adapters still require separate connection and cleanup tests.
- **Migration:** No broad inheritance migration is planned. Shared lifecycle behavior has two
  verified SSE/WebSocket consumers; protocol mechanics remain local.

## Compliance

- New manufacturer plugins reuse the shared transport and exception contracts.
- Protocol-specific code has fixture or mock-transport tests for authentication, response bounds,
  and streaming lifecycle.
- Integration clients do not own persistence, tenant scope, or domain orchestration.
- Test-only and unverified vendor API methods are removed rather than retained as compatibility
  surfaces.
