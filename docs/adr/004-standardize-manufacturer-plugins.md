---
title: "ADR-004: Manufacturer plugins share transport, not discovery"
description: "How manufacturer integrations are structured and which code may name a vendor."
type: explanation
audience: developer
---

## Context

Shure (REST plus WebSocket) and Sennheiser SSCv2 (REST plus an authenticated server-sent-event stream) have different protocols. Two consumers do not justify a broad inheritance tree, but safe transport, retries, rate limits and health tracking should not be copied per vendor.

## Decision

- Shared, verified transport and the plugin contract live in `micboard/services/common/base/`. Exceptions live in `micboard/exceptions.py` ([ADR-009](009-consolidate-exception-hierarchy.md)).
- Discovery, device endpoints and streaming adapters stay manufacturer-local under `micboard/integrations/<code>/`. Extract a helper only when two live integrations need it.
- Payload normalization is shared. `micboard/services/common/base/device_normalizer.py` reads the common field spellings, and each integration supplies its device-family vocabulary as data in `normalizer.py`. A vendor whose payload differs implements `normalize_device` and `normalize_channels` itself.
- Every path that persists vendor data reads one typed shape: `NormalizedChassis`, `NormalizedChannel` and `NormalizedUnit` in `micboard/services/core/hardware.py`. No service reads a vendor key or a raw dictionary, and a chassis role comes from the device specification catalogue, not from matching words in a type string.
- `build_manufacturer_plugin(manufacturer)` in `services/common/base/plugin.py` is the one way to obtain a plugin. Outside `micboard/integrations/`, only the API-server connection surface (`services/integrations/api_server_service.py`), the admin connection checker and the managed-device polling gate in `services/sync/polling_api.py` may name a vendor. That gate admits only Shure, the sole API-server protocol implemented.
- The realtime lifecycle is shared. `services/realtime/subscription_runner.py` owns leasing, inventory selection and connection tracking. `subscription_lifecycle_service.py` owns normalization, persistence, chassis projection and broadcast. Each integration declares `realtime_transport` and implements `subscribe_to_chassis`.
- There are two polling surfaces and neither absorbs the other: `ManufacturerSyncService` (`services/manufacturer/sync.py`) syncs a whole manufacturer, and `services/sync/polling_api.py` polls one operator-registered chassis.
- Vendor clients expose only operations the plugin contract uses.

## Consequences

Safety fixes in the shared transport reach every vendor while protocol behavior stays readable next to its protocol. Each protocol still needs its own tests for authentication, bounded payloads, origin validation and connection lifecycle.
