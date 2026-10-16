---
title: "Research: Telemetry Storage, Alerting, and Live Fan-out at Country Scale"
---
**Question** ([#356](https://github.com/justprosound/django-micboard/issues/356), part of
[#321](https://github.com/justprosound/django-micboard/issues/321)): how do open-source monitoring
platforms store device telemetry, raise and route alerts, and fan live state out to browsers, and
which of those designs fit micboard at thousands of sites, many MSP tenants, and hundreds of
thousands of RF devices and units?

**Date:** 2026-10-16. All sources are public project documentation, licence files, and source
code, read on that date. Links point at default branches, so content may drift.

**Builds on:** ADR-012 (bounded live projections, on `main`), and ADR-014, ADR-015, and ADR-016
(typed normalized DTOs, capability protocols, database-backed backoff, and online-state
transitions, on `docs/rf-distribution-unit`). Edge listeners at each site forward normalized
telemetry to a central instance.

## Summary

1. **Don't centralize per-second meters.** At the target scale, per-second meters are on the
   order of a million samples a second (worked out in section 1.1). That is past what one
   PostgreSQL node takes comfortably, and it's at the documented ceiling of a single
   VictoriaMetrics node. Every platform surveyed keeps raw resolution briefly and near the
   source, then keeps aggregates for long periods: Zabbix history and trends, Netdata tiers,
   VictoriaMetrics downsampling. micboard should do the same. Per-second meters stay at the edge
   for the site's live view. Central receives **state transitions** and **one-minute
   min/max/avg rollups**. That's a few thousand rows a second, which plain PostgreSQL handles.
2. **Store telemetry in plain PostgreSQL with native range partitioning.** Retention is dropping
   a partition, and rollups are a Huey job that writes a Zabbix-style "trends" table.
   TimescaleDB's useful extras, which are compression, continuous aggregates, and retention and
   job policies, are all under the **Timescale License (TSL)**, not Apache-2.0. Treat TimescaleDB
   as an optional accelerator an operator may install, never as a requirement. VictoriaMetrics
   is the scale-out escape hatch, but its downsampling and per-series retention are
   **Enterprise-only**.
3. **Alerting: adopt Alertmanager's semantics, not its binary.** Implement inside Django a
   fingerprinted alert record and the evaluation rules from Prometheus and Zabbix (`for`,
   `keep_firing_for`, and Zabbix's recovery expression). Add a routing tree with
   `group_by`/`group_wait`/`group_interval`/`repeat_interval`, inhibition (site offline
   suppresses its devices), silences, and maintenance windows. Offer a webhook and Alertmanager
   API receiver so MSPs can route into their existing PagerDuty or Opsgenie-style stack.
4. **Live fan-out: aggregate on the server and subscribe by scope.** `channels_redis`
   `group_send` writes one copy per group member and silently drops messages at capacity
   (default 100), so a national group receiving every meter would melt. Keep Channels and
   Redis. Publish a national or tenant rollup snapshot every one to five seconds, and stream
   per-unit meters only on a site or room channel that a viewer has opened. Keep Centrifugo
   (Apache-2.0, documented at a million connections) as the step-up when Channels runs out
   of connection headroom.
5. **Ingest: edge to central over HTTPS batches first, NATS JetStream when needed.** The edge
   buffers durably, sends batches with an idempotency key, and central upserts with
   `ON CONFLICT`. That needs no new infrastructure. NATS (Apache-2.0) with leaf nodes and
   JetStream is the best-fit step-up: outbound-only edge links, `Nats-Msg-Id` dedupe, and
   `MaxAckPending` backpressure. Avoid Redpanda (BSL forbids offering it as a queuing service)
   and Redis 8+ (RSALv2/SSPLv1/AGPLv3 tri-licence) in the default bill of materials. Valkey
   (BSD-3-Clause) is the clean drop-in for Redis.

## Recommendations

| # | Option | License | Verdict | What micboard does with it | One-maintainer cost |
|---|---|---|---|---|---|
| 1 | PostgreSQL declarative range partitioning | PostgreSQL | **Adopt** | Partition sample and rollup tables by time. Retention drops or detaches old partitions, and a Huey job creates the next ones. | Low: no new service, one job. |
| 2 | pg_partman | PostgreSQL | **Adapt (optional)** | Allowed as an operator choice, but micboard's own Huey job manages partitions so that no extension is required. | Low, but it's an extension that managed PostgreSQL may not offer. |
| 3 | TimescaleDB Apache-2.0 edition | Apache-2.0 | **Adapt (optional)** | Schema stays hypertable-compatible, with the time column in every unique key. Only `create_hypertable` and `drop_chunks` are Apache-licensed. | Medium: extension upgrades are tied to PostgreSQL upgrades. |
| 4 | TimescaleDB Community (TSL) features: compression, continuous aggregates, policies, jobs | Timescale License | **Skip as a dependency** | Never required. An operator may enable them on their own database. | Licence review for every MSP that hosts it. |
| 5 | VictoriaMetrics single-node or cluster (OSS) | Apache-2.0 | **Adapt (scale-out, later)** | An optional remote-write sink for one-minute or per-second metrics when PostgreSQL is outgrown. vmalert works on it. | Medium: a second datastore to back up and upgrade. |
| 6 | VictoriaMetrics Enterprise downsampling and retention filters | Commercial | **Skip** | micboard does its own rollups before writing, or uses OSS stream aggregation. | Paid licence. |
| 7 | Prometheus TSDB | Apache-2.0 | **Skip as a store** | Keep the existing `/metrics` exposition for operators. Don't use it as micboard's telemetry store: it's single-node, has no tenancy, and defaults to 15 days. | Low to expose, high to make durable. |
| 8 | ClickHouse | Apache-2.0 | **Skip (revisit beyond about 100k rows a second)** | Its `TTL … GROUP BY` rollup design is noted for the future. | High: new query language, merges, and cluster operations. |
| 9 | Zabbix storage model (history and trends, housekeeper) | AGPL-3.0 (7.0+) | **Adapt (design)** | Copy the shape: a short raw history plus an hourly min/max/avg/count "trends" table kept for years. | None, it's a design. |
| 10 | LibreNMS storage (RRD and rrdcached) | GPL-3.0 | **Skip** | File-per-metric RRD needs shared storage for HA. | n/a |
| 11 | Netdata dbengine tiers | GPL-3.0+ agent; the UI is NCUL1, not open source | **Adapt (design)** | Copy the tiering: per-second for days at the edge, per-minute for months, and per-hour for years. Don't embed its UI. | None, it's a design. |
| 12 | Prometheus alert rules: `for` and `keep_firing_for` | Apache-2.0 | **Adopt (semantics)** | A pending state before firing, and a hold time before resolving, so alerts don't flap. | Low. |
| 13 | Alertmanager: routing tree, grouping, inhibition, silences, time intervals | Apache-2.0 | **Adopt (semantics) and integrate (receiver)** | Implement in Django. Optionally forward firing alerts to an external Alertmanager through its API. | Medium to build. Running Alertmanager is the operator's choice. |
| 14 | Zabbix recovery expressions, escalations, and maintenance | AGPL-3.0 | **Adapt** | Hysteresis thresholds for RF and battery, timed escalation steps, and maintenance windows that suppress notifications but keep recording data. | Low. |
| 15 | LibreNMS alert rules and transports | GPL-3.0 | **Skip (reference only)** | The SQL rule builder doesn't map to typed DTOs. Its transport list is a checklist of integrations MSPs expect. | n/a |
| 16 | Django Channels with `channels_redis` `RedisChannelLayer` | BSD-3-Clause | **Adopt (keep), with limits** | Scope-keyed groups, server-side aggregation, and per-group capacity settings. | Low, already deployed. |
| 17 | `RedisPubSubChannelLayer` | BSD-3-Clause | **Skip for now** | Beta status. Revisit if the list-based layer's per-member writes become the bottleneck. | Low. |
| 18 | Centrifugo OSS | Apache-2.0 | **Adapt (step-up)** | When Channels' connection count or memory runs out, Django publishes to Centrifugo over HTTP and browsers connect to Centrifugo. | Medium: one Go binary plus Redis or NATS. |
| 19 | PostgreSQL `LISTEN`/`NOTIFY` | PostgreSQL | **Adopt (narrow)** | Wake the aggregator on commit. The payload is a key, never the telemetry. | Low. |
| 20 | Edge HTTPS batch with idempotency key, plus `INSERT … ON CONFLICT` | n/a | **Adopt (first)** | The default edge-to-central path. | Low. |
| 21 | Redis Streams consumer groups (with Valkey) | BSD-3-Clause for Valkey; Redis 8+ is tri-licensed | **Adapt** | Central ingest buffer between the HTTP receiver and the writers, using `XACK` and `XAUTOCLAIM`. | Low: Redis is already present for Channels and Huey. |
| 22 | NATS with JetStream and leaf nodes | Apache-2.0 | **Adapt (step-up)** | Edge leaf node to central hub with dedupe and backpressure, when HTTPS batching isn't enough or edges need store-and-forward. | Medium: one Go binary at each end. |
| 23 | Apache Kafka (KRaft) | Apache-2.0 | **Skip** | Over-provisioned for one maintainer at this volume once rollups happen at the edge. | High. |
| 24 | Redpanda | BSL 1.1 | **Skip (licence trap)** | The BSL forbids offering it as a "Streaming or Queuing Service" to third parties. | n/a |

## 1. Time-series storage

### 1.1 Write-rate envelope

These figures are arithmetic from the target in #356, not measurements:

- 300,000 units × 4 metered fields (RF A, RF B, audio, battery) at 1 Hz is **1.2 million samples
  a second**. VictoriaMetrics documents a single node "works perfectly" at "1.5+ million samples
  per second" and "50+ million" active series ([README, capacity planning][vm-readme]). That
  puts per-second meters for the whole country at the limit of one node, before replication.
- The same units at one row per unit per minute (min/max/avg of each field) is **5,000 rows a
  second**. Batched with `COPY` or multi-row `INSERT` into a partitioned table, that is
  ordinary PostgreSQL work.
- Online/offline transitions (ADR-016 clause 4) and alarms are events, not samples. They are
  orders of magnitude rarer.

Cardinality (the number of distinct series) follows units × fields: about 1.2 million series.
That's well inside what every system surveyed supports. Cardinality only becomes a problem if
free-text labels such as performer names or frequencies go into series keys. They belong in
the relational model.

### 1.2 PostgreSQL native partitioning — PostgreSQL License — **Adopt**

- PostgreSQL supports range, list, and hash partitioning
  ([Table Partitioning][pg-part]).
- The docs make the retention argument directly: "Dropping an individual partition using
  `DROP TABLE`, or doing `ALTER TABLE DETACH PARTITION`, is far faster than a bulk operation.
  These commands also entirely avoid the `VACUUM` overhead caused by a bulk `DELETE`." `DETACH
  PARTITION … CONCURRENTLY` lowers the parent lock to `SHARE UPDATE EXCLUSIVE`.
- On scale, the planner "is generally able to handle partition hierarchies with up to a few
  thousand partitions fairly well, provided that typical queries allow the query planner to
  prune all but a small number of partitions." Daily partitions with 30-day raw retention, plus
  monthly rollup partitions kept for years, stay in the tens to low hundreds of partitions.
- `pg_partman` automates creating and dropping partitions under the PostgreSQL License
  ([LICENSE][partman-lic]). It is an extension, and managed PostgreSQL services may not offer
  it. A small Huey periodic job that runs `CREATE TABLE … PARTITION OF` ahead of time and drops
  expired partitions removes that dependency.

**Gap in micboard today:** `WirelessUnitSample` (`micboard/models/telemetry/sessions.py`) is one
unpartitioned table with a serial key, foreign-keyed through a session, indexed only on
`timestamp`. Retention on it means bulk `DELETE`. A partitioned table needs the partition key
(time) in its primary key, and changing that is a migration that needs approval
(`django-safemigrate`).

### 1.3 TimescaleDB — Apache-2.0 and TSL — **Adapt (optional), skip TSL as a dependency**

The editions page ([TimescaleDB editions][ts-editions]) splits features as follows:

- **Both editions:** `create_hypertable`, `show_chunks`, `drop_chunks`, `time_bucket`.
- **Community (TSL) only:** the columnstore (`add_columnstore_policy`,
  `convert_to_columnstore`), continuous aggregates (`refresh_continuous_aggregate`,
  `add_continuous_aggregate_policy`), `add_retention_policy`, `add_job` and the other job
  functions, `time_bucket_gapfill`, and `reorder_chunk`/`move_chunk`. The page says "many of
  the most recent features of TimescaleDB are only available in TimescaleDB Community Edition."

The **TSL trap** ([LICENSE-TIMESCALE][tsl]): section 2.2 bars using TSL software to provide
"database-as-a-service services" except as part of "Your Value Added Products or Services".
Section 3.10 defines those as offerings that are "not primarily database storage or operations",
that "add substantial value of a different nature", and whose users are prohibited "either
contractually or technically, from defining, redefining, or modifying the database schema."
An MSP hosting micboard probably qualifies. But that is a legal judgement each operator has to
make, and the TSL isn't an open-source licence. If micboard *required* TSL features, every
AGPL deployment would carry a non-free dependency. Zabbix shows the cost of using it anyway:
its TimescaleDB compression works only under the TSL build and "is not supported under
'apache' Apache 2.0 license" ([Zabbix TimescaleDB setup][zbx-ts]).

So micboard's own rollup and retention code stays in plain SQL and Huey. The schema stays
hypertable-compatible, so an operator who installs TimescaleDB can convert the tables
themselves.

### 1.4 VictoriaMetrics — Apache-2.0 core, Enterprise extras — **Adapt later**

- The single-node and cluster versions are Apache-2.0 ([README][vm-readme]). The single node
  defaults to 31-day retention via `-retentionPeriod`, and the cluster version adds
  multi-tenancy. The single node "does not support multitenancy."
- **Enterprise-only** ([Enterprise features][vm-ent]): downsampling
  (`-downsampling.period`), multiple retentions (`-retentionFilter`), multitenant vmalert, and
  Kafka integration, among others. Downsampling and per-dataset retention are the features a
  long-history telemetry store needs, so the OSS build means one retention for everything.
- OSS **stream aggregation** in vmagent and the single node can aggregate "by time and by
  labels before data is written" ([stream aggregation][vm-streamaggr]). That can replace
  Enterprise downsampling for the one-minute tier.
- **Cost:** one more stateful service with its own backup tooling. Worth it only when per-second
  history has to be central. Until then, PostgreSQL holds the one-minute tier.

### 1.5 Prometheus TSDB — Apache-2.0 — **Skip as a store**

Local storage "is not clustered or replicated", averages "1-2 bytes per sample", and defaults to
15 days of retention. Remote write exists to get past those limits
([Storage][prom-storage]). It is a pull model with no tenancy. micboard already exposes metrics
(`micboard/metrics.py`). Keep that for operators and don't build product features on it.

### 1.6 ClickHouse — Apache-2.0 — **Skip for now**

MergeTree `TTL` can `DELETE`, move parts `TO VOLUME`/`TO DISK`, or roll up with `GROUP BY`, where
"`GROUP BY` expression must be a prefix of the table primary key". TTL runs during background
merges, so expired rows can still appear until a merge happens
([MergeTree][ch-mergetree]). It's a strong design for per-second data at national scale, but it
brings a second query language and its own operations. Revisit only if central per-second
history becomes a requirement and VictoriaMetrics doesn't fit.

### 1.7 How the monitoring platforms do it

- **Zabbix** (AGPL-3.0 from 7.0, GPLv2 up to 6.4: [licence][zbx-lic]) keeps every value in
  *history* and hourly min/max/avg/count in *trends*. The housekeeper deletes both by
  per-item retention, and the docs' examples keep history briefly and trends for years
  ([History and trends][zbx-hist]). **This is the model to copy.**
- **LibreNMS** (GPL-3.0: [licence][lnms-lic]) writes RRD files, accelerated by rrdcached. HA
  needs "shared storage for the RRD files over NFS with GlusterFS or similar"
  ([RRDCached][lnms-rrdc]). InfluxDB and other exports run alongside RRD, not instead of it
  ([InfluxDBv2][lnms-influx]). Skip.
- **Netdata**'s dbengine keeps tier 0 per-second for 14 days, tier 1 per-minute for 3 months,
  and tier 2 per-hour for 2 years, at "~0.5 bytes per sample on disk"
  ([Database][nd-db]). The agent is GPL-3.0-or-later, but the bundled dashboard is under the
  **Netdata Cloud UI License (NCUL1)** ([README licence table][nd-readme],
  [REDISTRIBUTED.md][nd-redist]). That UI isn't open source and must not be embedded or
  copied. The tier design is the useful lesson.

## 2. Alerting

### 2.1 Prometheus rules — Apache-2.0 — **Adopt the semantics**

- `for` holds a new alert in **pending** until the condition has held for the duration.
- `keep_firing_for` keeps it firing after the condition clears, to "prevent situations such as
  flapping alerts" ([Alerting rules][prom-rules]).

For micboard: battery-low fires after it has held for 2 minutes, and RF-dropout uses
`keep_firing_for` so that a performer walking past a pillar doesn't page anyone twice.

### 2.2 Alertmanager — Apache-2.0 — **Adopt the semantics, integrate as a receiver**

- **Grouping** "categorizes alerts of similar nature into a single notification".
  **Inhibition** suppresses alerts "if certain other alerts are already firing". **Silences**
  "mute alerts for a given time" by matchers. For HA, don't put a load balancer between
  Prometheus and its Alertmanagers ([Alertmanager][am]).
- The routing tree sets `group_by` (with `'...'` to disable aggregation), `group_wait`
  (default 30s), `group_interval` (5m), `repeat_interval` (4h), `continue`, and
  `mute_time_intervals` or `active_time_intervals`. Receivers include email, PagerDuty,
  OpsGenie, VictorOps, incident.io, Slack, Microsoft Teams, Telegram, SNS, Webex, and generic
  webhooks ([Configuration][am-conf]).

**Fit:** micboard's `Alert` model (`micboard/models/monitoring/alert.py`) is one notification
row per user and channel. It has no fingerprint, so it can't dedupe, group, or inhibit.
Recommended split:

1. **Alert instance**, unique on `(tenant, rule, fingerprint of target labels)`, with states
   `pending`, `firing`, `resolved`, and `silenced`. Re-evaluations update that row and never
   insert a new one. That is the dedupe.
2. **Notification**, one row per group flush per receiver. The existing `Alert` rows become
   this.
3. **Route tree per tenant**, matching on tenant, site, severity, and device kind. The
   `group_by` default is `(tenant, site, rule)`, so a site losing 40 transmitters sends one
   message.
4. **Inhibition**: a "site edge offline" alert (ADR-016 online state applied to the edge
   listener) inhibits every device alert at that site. "Chassis offline" inhibits its units.
5. **Silences and maintenance windows** use matchers and a time range, and are tenant-scoped.
6. **External receiver**: POST firing and resolved alerts to an MSP's Alertmanager
   `/api/v2/alerts` or a generic webhook, so MSPs with existing on-call stacks don't duplicate
   routing.

Running Alertmanager as micboard's *own* engine would mean exporting alert state as Prometheus
series, plus a second config surface outside tenant-aware Django permissions. Skip that.

### 2.3 Zabbix — AGPL-3.0 — **Adapt**

- **Hysteresis**: with a recovery expression, "not only does the problem expression have to be
  FALSE, but also the recovery expression has to be TRUE", which is "useful to create
  hysteresis and avoid trigger flapping" ([Trigger expressions][zbx-trig]). For micboard, fire
  at RF below −85 dBm, and recover only at −80 dBm.
- **Escalations**: steps of at least 60 seconds each. Recovery messages go only to recipients
  who received a problem message ([Escalations][zbx-esc]).
- **Maintenance**: "with data collection", triggers still evaluate and notifications pause.
  Escalations for problems that began during maintenance start when it ends. "No data
  collection" maintenance stops storing data ([Maintenance][zbx-maint]). micboard should
  offer only the first kind: a rehearsal or show-load-in window that records but doesn't page.

### 2.4 LibreNMS — GPL-3.0 — **Reference only**

Rules are built from database fields, with an "Override SQL" escape hatch, and options for
recovery alerts, mute, and acknowledgement ([Rules][lnms-rules]). Arbitrary SQL rules don't fit
typed DTOs and tenant isolation. The roughly 58 transports in its sidebar are a useful list of
what MSPs expect to integrate with.

## 3. Live fan-out to browsers

### 3.1 Channels and `channels_redis` — BSD-3-Clause — **Keep, with limits**

- Defaults: `capacity` 100, `expiry` 60s, `group_expiry` 86400s, per-channel `channel_capacity`.
  "Once a channel is at capacity, it will refuse more messages." Passing several hosts shards
  the layer, but "changing the host list will lose some sharded data"
  ([channels_redis][chr]).
- `group_send` reads every member of the group and pushes a copy into each member's channel
  key with a Lua script, skipping channels over capacity
  ([`core.py` `group_send`][chr-core]). Cost is **O(group members) per message**, and
  overflow is silent.
- `RedisPubSubChannelLayer` uses Redis pub/sub instead and is "at Beta status".

**Fit:** micboard's `BroadcastService` (`micboard/services/notification/broadcast_service.py`)
already partitions sends by site and scope. The rule to add follows ADR-012's bounded
projections: **a group gets either per-unit meters for a bounded scope, or an aggregate
snapshot, never per-unit meters for an unbounded scope.**

- `site:<id>` and `room:<id>` groups get per-unit meter deltas, throttled to the edge's own
  rate and capped like ADR-012's ceilings.
- `tenant:<id>` and `national` groups get a **snapshot DTO** every one to five seconds: counts
  by online/offline/alarm per site, worst RF and battery per site, and the top N alarms. One
  aggregator task builds it, and every viewer gets the same message.
- Unchanged snapshots are not re-sent (ADR-016 clause 5).

### 3.2 Centrifugo — Apache-2.0 — **Step-up option**

- A standalone real-time server over WebSocket, SSE, HTTP-streaming, WebTransport, and gRPC,
  with Redis, Redis Cluster, or NATS as its broker. The backend publishes through an HTTP or
  gRPC server API ([Introduction][cf-intro]).
- The FAQ suggests "not putting more than 50-100k clients on one node", at about 30-50 KB of
  RAM per WebSocket ([FAQ][cf-faq]). The project's benchmark served **1 million WebSocket
  connections** on 20 pods and 5 Redis instances, delivering "28 million messages per minute"
  at around 200 ms p99 ([million-connection test][cf-million]).
- History windows with automatic **recovery** on reconnect replace hand-rolled
  "resend last state" logic.
- There is also a commercial Centrifugo PRO. Nothing in this design needs it.

**When:** browser connections, not devices, drive this. NOC wall screens and operator consoles
across many MSPs could reach tens of thousands of sockets. Until then Channels is enough, and
the publish call is the only seam: the BroadcastService publishes to Centrifugo's HTTP API
instead of `group_send`.

### 3.3 NATS as a fan-out bus — Apache-2.0

NATS is a fit for ingest (section 4). For browsers it would duplicate Centrifugo, which can
use NATS as its broker. Don't expose NATS to browsers.

### 3.4 PostgreSQL `LISTEN`/`NOTIFY` — **Narrow use**

Notifications are delivered only at commit. Identical payloads within one transaction fold
into one, and the payload "must be shorter than 8000 bytes", so the docs advise sending "the
key of the record" ([NOTIFY][pg-notify]). That makes it a good trigger for the aggregator
("site 42 changed") and a bad telemetry bus.

## 4. Ingest from edge collectors

### 4.1 Contract, whatever the transport

- **Idempotency:** each edge batch carries `(edge_id, sequence)` and each row carries
  `(unit_id, bucket_start)`. Central writes with `INSERT … ON CONFLICT DO UPDATE`, which
  "guarantees an atomic INSERT or UPDATE outcome … even under high concurrency"
  ([INSERT][pg-insert]). Replays are harmless.
- **Backpressure:** the edge keeps a durable outbox (SQLite or local PostgreSQL) and sends
  oldest first. Central returns `429` or `503` with `Retry-After`, and the edge applies the
  same `min(base·2ⁿ, cap)` plus jitter that ADR-016 uses for device polling.
- **What crosses:** typed normalized DTOs (ADR-014) for state transitions, one-minute rollup
  rows, and configuration inventory diffs. Raw per-second meters cross only on demand, while
  a central viewer has that site open.

### 4.2 HTTPS batch to Redis Streams to writers — **Adopt first**

Redis Streams consumer groups give at-least-once delivery with a pending entries list, `XACK`,
`XAUTOCLAIM` for crashed consumers, and `MAXLEN ~` capping ([Streams][redis-streams]). Redis is
already there for Channels and Huey. **Licence note:** Redis 8 and later are under
RSALv2, SSPLv1, or AGPLv3 at the user's choice. Redis 7.2 and earlier are BSD-3-Clause
([LICENSE.txt][redis-lic]). Valkey is BSD-3-Clause ([repo][valkey]). Document both as
supported, and recommend Valkey where an MSP's licence policy rejects the tri-licence.

### 4.3 NATS JetStream with leaf nodes — Apache-2.0 — **Step-up**

- A leaf node "opens an outbound connection to a remote NATS system". It only needs the site
  to make one connection out, which suits venue firewalls. A leaf running JetStream needs its
  own JetStream domain ([Leaf nodes][nats-leaf]).
- Streams dedupe on `Nats-Msg-Id` within a window (2 minutes by default). Discard `New`
  rejects writes when the stream is full ([Streams][nats-streams]).
- `MaxAckPending` (default 1000) pauses delivery until workers ack, and pull consumers let a
  worker pool share one cursor ([Consumers][nats-consumers]). That is backpressure built in.

**When:** if edges need store-and-forward across long outages larger than an outbox handles
comfortably, or if central ingest has to be split across nodes. The cost is one Go binary per
site and a small central cluster.

### 4.4 Kafka and lookalikes — **Skip**

Apache Kafka (Apache-2.0) solves a volume micboard avoids by rolling up at the edge, and it
costs the most to operate. **Redpanda** is under BSL 1.1, whose Additional Use Grant excludes
any "Streaming or Queuing Service" offered to third parties, including hosting providers
([bsl.md][redpanda-bsl]). That's a trap for an MSP product.

## 5. Recommended architecture

```text
TELEMETRY PATH
  device ──poll/subscribe──▶ EDGE listener (per site)
                              │  normalized DTOs (ADR-014), online state (ADR-016)
                              ├─ per-second meters ──▶ edge ring buffer (hours) ──▶ site live view
                              ├─ 1-min min/max/avg rollup per unit ─┐
                              └─ state transitions + alarms ────────┤
                                                                    ▼
                                                     durable outbox (SQLite/PG)
                                                                    │ HTTPS batch, (edge_id, seq)
                                                                    │ 429/Retry-After + jittered backoff
                                                                    ▼
  CENTRAL  ingest API ──▶ Redis/Valkey Stream (consumer group, XACK/XAUTOCLAIM)
                                   │
                                   ▼
                         writer workers ── COPY / INSERT … ON CONFLICT ──▶ PostgreSQL
                                                                    │
            unit_sample_1m      PARTITION BY RANGE (bucket) daily   │ raw tier: 30–90 days
            unit_sample_1h      PARTITION BY RANGE (bucket) monthly │ trends: 2–5 years
            state_transition    PARTITION BY RANGE (at)     monthly │ audit: per tenant policy
                                   ▲
            Huey periodic: roll 1m→1h, create next partitions, DETACH/DROP expired ones

ALERT PATH
  state transitions + 1m rollups
      ──▶ rule evaluator (Huey / realtime process)
            for / keep_firing_for, hysteresis (problem vs recovery threshold)
      ──▶ AlertInstance  UNIQUE(tenant, rule, fingerprint)   ← dedupe
      ──▶ inhibition (edge offline ⊃ chassis offline ⊃ unit alerts), silences, maintenance
      ──▶ per-tenant route tree  group_by(tenant, site, rule)
            group_wait 30s · group_interval 5m · repeat_interval 4h · escalation steps
      ──▶ receivers: email · SMS gateway · webhook · Alertmanager /api/v2/alerts
                     (PagerDuty / Opsgenie-style via the MSP's own stack)

LIVE PATH
  writer / edge relay ──NOTIFY key──▶ aggregator (one per central node, leader-elected)
      ├─ site:<id>, room:<id>  ← per-unit meter deltas, bounded (ADR-012), only while watched
      └─ tenant:<id>, national ← snapshot DTO every 1–5 s (counts, worst RF/battery, top-N alarms)
                                   skip if unchanged (ADR-016 §5)
      ──▶ Channels group_send (Redis/Valkey)      [step-up: Centrifugo HTTP publish]
      ──▶ browser (HTMX / WebSocket)
```

**Smallest viable deployment** (one site, or a small MSP): one host running PostgreSQL,
Valkey or Redis, Django, Daphne or Uvicorn, Huey, and the realtime process. The "edge" is the
same process, and the outbox is a table in the same database. Partitioning and rollups still
run, because they cost nothing at small scale and avoid a migration later.

**Scaling up, in order, each step only when a measurement demands it:**

1. **Split edge from central.** Edge listeners at each site send HTTPS batches to central.
   That's the contract above.
2. **Scale central horizontally.** Run several stateless ingest, writer, and web nodes. Use a
   PostgreSQL primary with a read replica for dashboards and history queries, and a separate
   Valkey for channel layers versus the Huey queue.
3. **Move browser fan-out to Centrifugo** when socket count or memory per node becomes the
   limit.
4. **Switch the edge-to-central transport to NATS leaf nodes and JetStream** when edges need
   long store-and-forward or ingest needs to be split across nodes.
5. **Add VictoriaMetrics** (OSS, stream-aggregated) only if per-second history must be central.
   PostgreSQL stays the system of record for inventory, state, and alerts.
6. **Optional, operator's choice:** TimescaleDB on the same schema. An operator who accepts the
   TSL may enable compression and continuous aggregates.

## Open questions for follow-up tickets

- The partitioned replacement for `WirelessUnitSample` needs an ADR and an approved migration.
  Its primary key would change to `(unit_id, bucket_start)`, the session foreign key would
  become a plain column, and the table would be partitioned by range.
- The alert model split (instance vs notification) needs an ADR and a migration.
- The edge-to-central wire format (versioned DTO envelope, signing, and per-edge credentials)
  isn't covered here. It belongs with the edge-listener ticket in #321.

[pg-part]: https://www.postgresql.org/docs/current/ddl-partitioning.html
[pg-notify]: https://www.postgresql.org/docs/current/sql-notify.html
[pg-insert]: https://www.postgresql.org/docs/current/sql-insert.html
[partman-lic]: https://github.com/pgpartman/pg_partman/blob/master/LICENSE.txt
[ts-editions]: https://www.tigerdata.com/docs/about/latest/timescaledb-editions
[tsl]: https://github.com/timescale/timescaledb/blob/main/tsl/LICENSE-TIMESCALE
[vm-readme]: https://github.com/VictoriaMetrics/VictoriaMetrics/blob/master/docs/victoriametrics/README.md
[vm-ent]: https://github.com/VictoriaMetrics/VictoriaMetrics/blob/master/docs/victoriametrics/enterprise.md
[vm-streamaggr]: https://github.com/VictoriaMetrics/VictoriaMetrics/blob/master/docs/victoriametrics/stream-aggregation/README.md
[prom-storage]: https://prometheus.io/docs/prometheus/latest/storage/
[prom-rules]: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
[am]: https://prometheus.io/docs/alerting/latest/alertmanager/
[am-conf]: https://prometheus.io/docs/alerting/latest/configuration/
[ch-mergetree]: https://clickhouse.com/docs/engines/table-engines/mergetree-family/mergetree
[zbx-lic]: https://www.zabbix.com/license
[zbx-hist]: https://www.zabbix.com/documentation/current/en/manual/config/items/history_and_trends
[zbx-ts]: https://www.zabbix.com/documentation/current/en/manual/appendix/install/timescaledb
[zbx-trig]: https://www.zabbix.com/documentation/current/en/manual/config/triggers/expression
[zbx-esc]: https://www.zabbix.com/documentation/current/en/manual/config/notifications/action/escalations
[zbx-maint]: https://www.zabbix.com/documentation/current/en/manual/maintenance
[lnms-lic]: https://github.com/librenms/librenms/blob/master/LICENSE.txt
[lnms-rrdc]: https://docs.librenms.org/Extensions/RRDCached/
[lnms-influx]: https://docs.librenms.org/Extensions/metrics/InfluxDBv2/
[lnms-rules]: https://docs.librenms.org/Alerting/Rules/
[nd-db]: https://learn.netdata.cloud/docs/netdata-agent/database
[nd-readme]: https://github.com/netdata/netdata/blob/master/README.md
[nd-redist]: https://github.com/netdata/netdata/blob/master/REDISTRIBUTED.md
[chr]: https://github.com/django/channels_redis
[chr-core]: https://github.com/django/channels_redis/blob/main/channels_redis/core.py
[cf-intro]: https://centrifugal.dev/docs/getting-started/introduction
[cf-faq]: https://centrifugal.dev/docs/faq
[cf-million]: https://centrifugal.dev/blog/2020/02/10/million-connections-with-centrifugo
[redis-streams]: https://redis.io/docs/latest/develop/data-types/streams/
[redis-lic]: https://github.com/redis/redis/blob/unstable/LICENSE.txt
[valkey]: https://github.com/valkey-io/valkey
[nats-leaf]: https://docs.nats.io/running-a-nats-service/configuration/leafnodes
[nats-streams]: https://docs.nats.io/nats-concepts/jetstream/streams
[nats-consumers]: https://docs.nats.io/nats-concepts/jetstream/consumers
[redpanda-bsl]: https://github.com/redpanda-data/redpanda/blob/dev/licenses/bsl.md
