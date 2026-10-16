---
title: "ADR-025: Passive Media Network Observation"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

Wireless systems feed Dante, AES67, and SMPTE ST 2110 media networks. Those networks fail in
ways operators need to see: a PTP grandmaster lost, a stream gone, packet loss, a Dante device
offline. They live on isolated segments that must not be bridged (ADR-018). Decided in
[#388](https://github.com/justprosound/django-micboard/issues/388), from the research in [#376](https://github.com/justprosound/django-micboard/issues/376).

## Decision

1. Media network monitoring is a sibling area inside micboard. It shares tenancy, Edge
   Listeners, alerting, and the UI with RF monitoring.
2. A **Media Segment Collector** is a segment collector (ADR-018) with media capabilities. It
   emits only scrubbed DTOs, which carry no network addresses.
   - **Always on, passive:** a PTP observer (grandmaster, clock class, and changes), a SAP/SDP
     listener, an mDNS browser, a Dante heartbeat listener, and read-only RAVENNA SDP fetches.
   - **Opt-in:** an audio loss probe that joins audio flows only, capped per host and never ST
     2110-20 video, and a probe clock that runs PTP as a follower to measure offset.
3. An AMWA NMOS IS-04 registry and the Dante Managed API connect as Device Manager plugins
   (ADR-015), read-only. The Dante control-port protocol is not used.
4. linuxptp (GPL-2.0-or-later) runs only as an external process. Scapy (GPL-2.0-only) isn't
   used. Protocol parsers are written on the standard library.
5. Alerts (ADR-020): grandmaster changed or absent, PTP offset (probe clock only), an Expected
   Flow missing, RTP loss, and a Dante device offline. A grandmaster loss inhibits the flow
   alerts in its domain.

## Consequences

- New models: Media Endpoint, Media Flow, Flow Leg, PTP Domain, and Dante Domain, delivered in
  phases (models, then PTP, SAP and RAVENNA, Dante passive, NMOS, loss probe, managed APIs, and
  the probe clock).
- A follower's PTP offset can only be seen with the opt-in probe clock.

## Alternatives considered

- **A separate media-monitoring product:** rejected, because it would duplicate tenancy, edges,
  and alerting.
- **Capturing whole streams centrally:** rejected, because it bridges segments and costs
  bandwidth.
