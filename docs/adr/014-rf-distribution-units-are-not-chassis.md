---
title: "ADR-014: RF Distribution Units Are Not a Chassis RF Role"
---
**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Project team

## Context

Combiners and splitters (for example Wisycom's MAT and SPL ranges) sit between antennas and
wireless chassis. Operators need them in inventory, need to know which receivers lose RF when
one fails, and need the alarms that managed units report.

`WirelessChassis` gives every chassis one RF role, receiver, transmitter, or transceiver, and
its docstring says that hardware which fits none of them is "a signal to revisit the
architecture rather than patch with new roles". A distribution unit fits none of them: it is
not an RF endpoint, has no RF channels, and no field unit connects to it. It has ports, gain or
attenuation, and supply and thermal state.

## Decision

1. An **RF Distribution Unit** is its own model, not a fourth chassis role. Its direction is
   `combiner` or `splitter`. The vocabulary lives in `CONTEXT.md`.
2. It follows the `Charger` precedent: a unit with child **Distribution Port** rows (port number,
   input or output).
3. A distribution port may link to the `WirelessChassis` it feeds or is fed by, with a free-text
   label for the antenna side. No Antenna model is introduced.
4. A capability flag marks **managed** units. Unmanaged (passive) units are inventory and
   topology only and are never polled.
5. Ownership runs through `location`, building, and organization, like `Charger` and
   `WirelessChassis`, so `visible_to` scopes it without a special case. Ports inherit their
   unit's visibility.
6. Telemetry is vendor-neutral and nullable. On the unit: status, online state, last seen,
   firmware, temperature, supply health, and a list of normalized alarm codes. On each port: RF
   level in dBm, gain in dB (negative for attenuation), and an alarm. A field a vendor does not
   report stays null.
7. **Amended 2026-10-16 ([#374](https://github.com/justprosound/django-micboard/issues/374)):**
   readings are stored as the vendor's raw value plus its unit. dBm or dB are derived only where
   the plugin documents the conversion, and are marked as derived (ADR-019).

## Consequences

- Chassis roles and RF channel directions stay as they are. No polling, alert, or dashboard code
  that branches on role has to learn about a non-endpoint.
- Topology from ports to chassis makes it possible to answer "which receivers lose RF if this
  splitter fails", but raising alerts on those receivers is not decided here.
- A later Antenna model can attach to the port's antenna side without changing ports to chassis.
- Introducing the models needs a migration, which ships through `django-safemigrate` like any
  other schema change.

## Alternatives considered

- **A fourth chassis role.** Rejected: every role-aware code path would need a branch for
  hardware that has no channels and no field units, which is the patch the chassis docstring
  warns against.
- **An `Accessory` category.** Rejected: accessories have no telemetry and no relationships, so
  topology and alarms would have nowhere to live.
- **Ports stored as JSON on the unit.** Rejected: ports need foreign keys to chassis and their
  own alarm state.
