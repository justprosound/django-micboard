---
title: "Device discovery workflow"
description: "How discovered devices are matched to existing inventory, staged for review and imported."
type: explanation
audience: both
---
Discovery finds devices on the network or through a manufacturer API and decides, for each one, whether it is new, already known, moved, or in conflict with existing inventory. Nothing a person must judge is imported silently: those devices wait in a review queue.

## Matching a device to inventory

`micboard/services/deduplication/check.py::check_device` compares a candidate with existing `WirelessChassis` rows in a fixed order and stops at the first decisive match:

1. **Serial number**, the primary identity.
2. **MAC address**, canonicalized so formatting differences do not matter.
3. **IP address**.
4. **Manufacturer API device id**, within one manufacturer.

Before those, a durable-identity check rejects a candidate whose serial or MAC belongs to a chassis of a different manufacturer, and a candidate whose serial and MAC resolve to two different chassis (`durable_identity_mismatch`).

The result is a `DeduplicationResult` with exactly one outcome:

| Outcome | Meaning | Typical cause |
| --- | --- | --- |
| `new` | No identity matched | A device not seen before |
| `duplicate` | The same device at the same address | A repeat sighting; metadata and last-seen are refreshed |
| `moved` | The same device, new address (`conflict_type="ip_changed"`) | DHCP change or re-addressing |
| `conflict` | Identities disagree (for example a different device already holds the IP) | Address reuse or a mismatched record |

## The review queue

Candidates that need a decision are staged as `DiscoveryQueue` rows with a status of `pending`, `approved`, `rejected`, `imported` or `duplicate`. Flags on the row (`is_duplicate`, `is_ip_conflict`, `is_duplicate_api_id`) and the `existing_device` or `existing_charger` link say what the candidate collided with.

Approval is atomic and bounded. `micboard/services/sync/discovery_approval_service.py::DiscoveryApprovalService` plans the approval, checks the reviewer's permissions and IP ownership, writes chassis through the chassis persistence service ([ADR-002](../adr/002-extract-model-business-logic.md)), and marks the rows `imported`. One approval handles at most `MAX_DISCOVERY_APPROVAL_BATCH` rows (100, in `micboard/discovery/limits.py`).

## Movement history

When a known device appears at a new address or location, a `DeviceMovementLog` row records the old and new IP and location, the movement type, who or what detected it and why. An operator acknowledges it from the admin, which sets `acknowledged`, the time and the user.

## Where it runs

Discovery services live in `micboard/services/sync/` (`discovery_service.py` and its execution, trigger, queue, claim, approval and source-cursor modules). Discovery sources are `DiscoveryCIDR` and `DiscoveryFQDN` rows and the manufacturer APIs. To run discovery by hand, see [Review discovered devices](review-discovery-queue.md) and the `sync_discovery` and `discovery_add_devices` commands in the [management commands reference](../api/reference/management-commands.md).
