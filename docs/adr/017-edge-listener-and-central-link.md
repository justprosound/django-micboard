---
title: "ADR-017: Edge Listeners and the Link to Central"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

RF gear announces itself with link-local multicast (Shure SLP, Sennheiser mDNS and MCP, the
Audio-Technica multicast group). That multicast doesn't cross routers. Some devices accept only
one TCP client. Sites sit behind NAT and firewalls micboard doesn't control. A show must not
stop when the WAN does. Decided in [#355](https://github.com/justprosound/django-micboard/issues/355), [#371](https://github.com/justprosound/django-micboard/issues/371), and [#378](https://github.com/justprosound/django-micboard/issues/378).

## Decision

1. An **Edge Listener** is the micboard package running with an `edge` settings profile on one
   **Campus**. It is the session-owner process from the transport decision, made deployable.
   Single-site installs run it beside central.
2. The edge owns discovery listening, device sessions, polling, per-second meters, 1-minute
   rollups, local alert evaluation, and scrubbing. Central owns tenancy, history, routing,
   notifications, the API, and fleet management.
3. The edge opens one **outbound WSS** connection to central, authenticated by a Knox token
   issued at enrolment. Central derives the tenant from that enrolment, never from a message.
   - **Up:** sequence-numbered envelopes, acknowledged by central and idempotent on
     `(edge_id, seq)`.
   - **Down:** heartbeats, revision-hashed layered config, credential rotation, refresh
     requests, and live-meter subscriptions. **Never device writes.**
4. A SQLite outbox (WAL, `synchronous=FULL`) buffers for up to 1 hour. Live state collapses to
   the latest snapshot per device.
5. Version checks: central refuses an edge newer than itself and supports edges up to N−1
   minor versions behind.
6. A Campus may run two edges. Central gives each device's session to one edge under a lease,
   which moves to the peer on heartbeat loss, so single-client devices keep a single owner.
7. **Autonomy:** an edge can serve a local, read-only live board on a dedicated operator
   interface, with operator tokens validated offline and a break-glass PIN. Central stays the
   system of record and de-duplicates alerts on reconnect.

## Consequences

- No inbound port is opened at any site, and central never initiates a connection to a site.
- Central's recovery time must stay under the edge buffer window.
- One codebase and one process type serve single-site, multi-campus, and national deployments.

## Alternatives considered

- **Relaying discovery** (mDNS or SLP reflectors, IGMP proxying): rejected. It invites storms
  and one-client conflicts, and it bridges segments.
- **MQTT, gRPC, or mTLS with a private CA:** rejected as too much infrastructure for one
  maintainer. WSS over TLS with per-edge credentials gives the needed assurance.
- **A UI-less edge:** rejected. A campus must stay monitorable during an outage.
