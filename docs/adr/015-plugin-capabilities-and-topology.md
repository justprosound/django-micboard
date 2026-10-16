---
title: "ADR-015: Plugin Capabilities and Topology"
---
**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Project team
**Supersedes:** ADR-004 clauses 6 (the source of `realtime_transport`) and 9 (the Shure-only
managed-device gate)

## Context

ADR-004 shaped the plugin contract around two vendors that both speak HTTP. The vendor
landscape research found that supporting the rest of the market needs more:

- **Two topologies.** Some vendors are reached through a **Device Manager** (Shure System API,
  Wisycom Manager), others device by device (Sennheiser, Audio-Technica, Lectrosonics).
- **Three update models:** a stream from a server, pushes after a subscribe, or polling only.
- **Transports beyond HTTP:** TCP, UDP and multicast, and Ember+.
- **Device kinds beyond the chassis:** chargers and RF Distribution Units (ADR-014).
- **Tiers:** some vendors can be verified against captured fixtures and others cannot.

One abstract base class, with `NotImplementedError` stubs and a two-value `realtime_transport`
literal, can express none of this. ADR-004 clause 9 hard-codes the managed-device polling gate
to Shure.

## Decision

1. Plugins return typed normalized objects for every device kind: `NormalizedChassis`,
   `NormalizedChannel`, and `NormalizedUnit` (from the change that added ADR-004 clause 10), plus
   `NormalizedCharger` and `NormalizedDistributionUnit`/`NormalizedDistributionPort`.
2. Capabilities are `typing.Protocol`s, one each for inventory, realtime stream, push
   subscription, discovery, and health. A plugin implements only the ones that apply, and
   orchestration checks which protocols a plugin implements rather than reading flags.
3. Facts that aren't methods live in a frozen `PluginTraits` DTO on the plugin:
   - topology: through a Device Manager, or direct;
   - tier: verified or unverified;
   - session limit;
   - poll interval, for poll-only vendors;
   - read-only policy: the allowlist every transport enforces.
4. **Device Manager** is vendor-neutral. A plugin with manager topology connects through one,
   and the managed-device polling gate checks topology instead of naming a vendor. The persisted
   connection links to the existing `Manufacturer` record rather than to a vendor enum.
5. Ownership follows the transport decision: Huey polls stateless HTTP devices. The long-running
   realtime process owns every session-based device, including poll-only ones over TCP.
6. A test fails when a plugin's declared tier disagrees with whether captured fixtures exist
   for it.

## Consequences

- ADR-004 clauses 1–5, 7, 8 and 10 still hold. Clauses 6 and 9 are superseded here and get
  marked as such when the contract change lands.
- Outside `micboard/integrations/`, no module names a vendor, without exceptions.
- Moving the persisted manager connection off its vendor enum needs a migration.
- Shure and Sennheiser move onto the new contract in one change before any new vendor is added.

## Alternatives considered

- **Capability flags on the existing base class.** Rejected: declared flags and implemented
  methods can drift apart, while a protocol is satisfied only by code that exists.
- **Amending ADR-004 again.** Rejected: it already carries a correction note, and a third layer
  of amendment would hide which clauses are current.
