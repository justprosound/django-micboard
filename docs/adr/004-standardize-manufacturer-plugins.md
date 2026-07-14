# ADR-004: Compose Manufacturer Plugins Around Shared Transport

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-14
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
4. Keep `PluginRegistry` as the construction boundary and manufacturer sync services as the
   persistence and orchestration boundary.
5. Contract-test each protocol against authoritative behavior, including authentication, bounded
   payloads, origin validation, and connection lifecycle.
6. Share the transport-neutral subscription lifecycle in
   `services/realtime/subscription_lifecycle_service.py`: eligible inventory selection, transform,
   persistence, chassis projection, and broadcast. Keep connection setup, authentication, event
   framing, and cleanup in each transport adapter.

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
