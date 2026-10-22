---
title: "ADR-019: Telemetry Pipeline, Storage, and Live Fan-out"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

At country scale (about 300k units), per-second meters come to about 1.2M samples/s. That's at
the limit of a single time-series node, and far beyond what operators need centrally. Decided
in [#365](https://github.com/justprosound/django-micboard/issues/365) and [#367](https://github.com/justprosound/django-micboard/issues/367), from the scale research ([#356](https://github.com/justprosound/django-micboard/issues/356)).

## Decision

1. Per-second meters stay at the edge for 24 h. Central receives 1-minute min/max/avg rollups
   and discrete state changes, about 5k rows/s.
2. Ingest: the WSS consumer appends to a **Valkey** Stream (BSD; Redis 8+ is RSAL/SSPL/AGPL).
   Writers upsert with `ON CONFLICT DO NOTHING` into **PostgreSQL tables partitioned by time**,
   with daily partitions created ahead by Huey.
3. Retention: 1-minute rollups for 30 days, hourly for 2 years, and state changes and alerts for
   2 years. Tenants may shorten these, never lengthen them. Expiry drops partitions.
4. Telemetry stores the **vendor's raw value plus its unit**. A converted value (for example
   dBm) is stored only where the plugin documents the conversion, and is marked as derived.
5. **Live meters are streamed on demand:** central subscribes an edge to a view's unit set only
   while a room, site, or Event view is open. Tenant, region, and national views get aggregate
   snapshots every 1–5 s. Channels on Valkey carry it, with Centrifugo above about 10k sockets.

## Consequences

- No TimescaleDB, VictoriaMetrics, ClickHouse, or Kafka is needed to start. Scale-up path:
  split nodes, then NATS JetStream, then optional VictoriaMetrics.
- `WirelessUnitSample` migrates to a partitioned table by expand and contract.

## Alternatives considered

- **TimescaleDB:** compression and continuous aggregates are under the TSL licence.
- **VictoriaMetrics:** downsampling is Enterprise-only.
- **Streaming every meter centrally:** rejected on cost and fragility.
