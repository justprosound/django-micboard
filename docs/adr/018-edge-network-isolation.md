---
title: "ADR-018: Edge Listener Network Isolation"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

Enterprises put wireless and media hardware on many isolated subnets that are routed for campus
connectivity but must stay segmented. An Edge Listener has to observe those segments without
ever becoming a path between them, or into the enterprise network. The same holds for Dante,
AES67, and SMPTE ST 2110 media networks. Decided in [#375](https://github.com/justprosound/django-micboard/issues/375) and amended by
[#378](https://github.com/justprosound/django-micboard/issues/378).

## Decision

1. **An edge observes; it never forwards.** Only normalized, scrubbed DTOs leave a segment,
   over the one outbound link (ADR-017). No packet, frame, multicast group, or announcement is
   forwarded, bridged, routed, reflected, or proxied.
2. One host attaches over an 802.1Q trunk. Each segment's VLAN sub-interface lives in **its own
   network namespace**, with one segment collector process per namespace. The uplink and the
   optional operator interface each have their own namespace. Collectors reach the uplink only
   through Unix domain sockets.
3. **Host controls:**
   - forwarding off in every namespace;
   - no bridges, `proxy_arp=0`, and `mc_forwarding=0`;
   - no multicast routing daemons and no mDNS or SLP reflection;
   - nftables with a default-drop forward chain;
   - on segments, outbound only to the plugin's documented read ports;
   - on the uplink, outbound only to central, with no listening ports.
4. Container deployments use one macvlan or ipvlan container per segment, with no route to the
   management network.
5. A self-check verifies all of this **before starting** and **refuses to start** on any
   violation. It re-runs periodically, raises a critical alert on drift, and reports its status
   in heartbeats. CI proves that no packet crosses between two namespaces.

## Consequences

- The read-only guard (ADR-016) and the segment-side nftables output rules are two independent
  layers against writes.
- Adding devices by IP from central, without an edge, remains a choice for the network team.

## Alternatives considered

- **A single multi-homed process:** rejected, because one routing table could bridge segments.
- **A VM per segment:** rejected as heavier, with no isolation gain over namespaces.
