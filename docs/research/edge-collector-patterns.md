---
title: "Research: Edge Collector Patterns for Isolated Networks and Sites"
---
**Question** ([#354](https://github.com/justprosound/django-micboard/issues/354), part of
[#321](https://github.com/justprosound/django-micboard/issues/321)): how do mature open-source
monitoring systems run collectors inside isolated network segments and sites, and what should
micboard borrow for an **edge listener**? The edge listener is a process deployed per segment or
site. It listens for discovery traffic that doesn't cross routers, owns device sessions locally,
and forwards normalized telemetry to central micboard.

**Date:** 2026-10-16. All sources are public. Links point at each project's current docs or
default branch as read on that date. Claims marked *unverified* could not be confirmed from a
primary source and should be measured on hardware before a design depends on them.

## Summary

1. **Every mature system has the edge connect outbound to the centre.** Zabbix active proxies,
   Netdata children, Grafana Alloy `remotecfg`, OpAMP clients, and Bitfocus Companion Satellite
   all open the connection from the edge. The centre never needs a route into the site.
2. **Collecting locally beats relaying discovery in micboard's case.** mDNS (`224.0.0.251`) is
   link-local and can never be routed. Discovery only yields an address, and every vendor session
   needs unicast reachability afterwards. Audio-Technica's multicast group carries live state, not
   only discovery. Reflecting multicast into an isolated VLAN also breaks the isolation.
3. **Every edge buffer is bounded, and each system documents how much data it loses.**
   Prometheus keeps 2 h, Zabbix keeps 1 h by default, Alloy up to 8 h, and Netdata replicates up
   to 1 day. micboard reports *state*, not a time series. So the edge can coalesce to the latest
   state per target and keep only transitions and alerts in a durable outbox.
4. **Version skew is handled with a handshake plus explicit tiers.** Companion Satellite sends an
   additive semver `ApiVersion` in its greeting. Zabbix classes a proxy as *current*, *outdated*
   (still sends data, gets no configuration), or *unsupported* (refused).
5. **Enrolment follows Kubernetes bootstrap tokens and Netdata claim tokens.** A short-lived,
   single-use token is exchanged for a per-edge credential. The centre stores the credential
   hashed, deleting it revokes it, and the centre then closes the live connection.
6. **Packaging is one multi-arch container image plus a `uv tool install` and systemd route** for
   Raspberry Pi OS. Raspberry Pi OS (Trixie) ships Python 3.13, which matches micboard's target.
   Single-binary builds and prebuilt OS images cost more maintenance than one maintainer should
   carry.

For the transport, micboard already ships `channels` and `websockets` and has an ASGI WebSocket
route (`micboard/websockets/routing.py`). **One outbound WSS connection per edge** therefore
adds no new infrastructure. MQTT needs a broker, and gRPC needs a second HTTP/2 server plus code
generation.

## Recommendations

| # | Pattern (source) | Verdict | Concrete change to micboard |
|---|---|---|---|
| 1 | Edge dials out; the centre never connects in (Zabbix active proxy, Netdata child, Companion Satellite, OpAMP) | **Adopt** | The edge listener opens one outbound WSS connection to central micboard. Central holds no route, port forward, or VPN into a site. |
| 2 | Collect locally rather than relay discovery (RFC 6762, RFC 5771, RFC 8766) | **Adopt** | The edge listener runs the discovery service and the realtime process inside the segment. Discovery multicast never leaves the link. |
| 3 | Avahi reflector / `mdns-repeater` | **Skip** | Can't carry state traffic, has loop risk, and exposes both segments to each other. Document it as an operator option for trusted, already routed segments only, filtered to `_ssc._udp`/`_ssc._tcp`. |
| 4 | RFC 8766 Discovery Proxy (unicast, on demand, rate-limited) | **Adapt** | The edge listener is effectively a purpose-built discovery proxy. Borrow its rate limit on generated multicast and its "answer only what was asked" scope. Don't implement DNS. |
| 5 | SLP Directory Agent (RFC 2608) | **Skip** | No evidence Shure devices register with a DA (*unverified*). Shure's group `239.255.254.253:8427` isn't RFC 2608's. A passive listen at the edge is enough. |
| 6 | IGMP proxying (RFC 4605), static multicast routing | **Skip** | Useless for link-local groups. For Shure's local-scope and Audio-Technica's reserved-range groups, it depends on sender TTL (*unverified*) and network changes micboard doesn't own. |
| 7 | Add by IP when unicast is already routed (Sennheiser Control Cockpit, Dante Domain Manager static enrolment) | **Adopt** | Keep "add device by IP" on central as the no-edge path. An edge listener is only needed where central can't reach the devices or discovery is required. |
| 8 | Central is authoritative for configuration, which is pulled and versioned (Zabbix proxy sync, Alloy `remotecfg`, OpAMP remote config) | **Adopt** | Central assigns targets to an edge. The edge receives its target list with a revision number over the connection and caches the last good copy locally. |
| 9 | Durable, bounded outbox with a stated loss horizon (Zabbix `ProxyOfflineBuffer`, Prometheus WAL, OTel `file_storage` queue) | **Adapt** | Use a SQLite outbox for transitions and alerts, bounded by age (default 1 h) and size, dropping the oldest. Coalesce live state to the latest DTO per target rather than replaying it. |
| 10 | Retry rules: retry 5xx and 429 with backoff and `Retry-After`, never retry other 4xx (Prometheus Remote-Write 2.0, OTLP) | **Adopt** | The same rules apply to the enrolment and fallback HTTPS calls. Over WSS, close codes in 4000–4999 carry the "don't retry" cases (revoked, schema unsupported). |
| 11 | Flow control by an in-flight window (MQTT 5 Receive Maximum, OTel `memory_limiter`, `websockets` write limits) | **Adopt** | The edge keeps at most *N* unacknowledged frames. Central acknowledges by sequence number, so a slow central throttles the edge, which then coalesces. |
| 12 | Idempotent receive keyed by sender and sequence (Prometheus Remote-Write 2.0) | **Adopt** | Each frame carries `edge_id` and a monotonic `seq`. Central keeps a high-water mark per edge and ignores replays. |
| 13 | Version handshake plus skew tiers (Companion Satellite `BEGIN … ApiVersion`, Zabbix compatibility matrix) | **Adopt** | The edge's `hello` frame declares a semver schema version. Same major and older minor: accepted. Edge newer than central: refused with a 4000-range close code. Additive changes only within a major. |
| 14 | Bootstrap token exchanged for a per-node credential (Kubernetes bootstrap tokens, Netdata claim token) | **Adopt** | An admin creates an edge, gets a single-use `id.secret` token with a 1 h expiry, and the edge exchanges it once over HTTPS for a long-lived credential. Both are stored hashed, and the credential is write-only per ADR-016 clause 7. |
| 15 | Revocation by deleting the server-side record (Knox, Netdata token regeneration) plus closing live sessions | **Adopt** | Revoking an edge deletes its credential and closes its socket with a revoked close code. The edge stops and doesn't retry. |
| 16 | mTLS with CSR bootstrap and short-lived certificates (kubelet TLS bootstrap, step-ca, SPIRE, OpAMP) | **Skip for now** | Needs a CA, proxy configuration, and certificate forwarding. Revisit only if a deployment requires mutual TLS. `cryptography` can build CSRs when that day comes. |
| 17 | Overlay VPN for edge reachability (Tailscale, headscale) | **Skip** | Outbound WSS already crosses NAT. A VPN is the operator's choice, not micboard's dependency. |
| 18 | MQTT broker between edge and centre (Telegraf `mqtt` output, Mosquitto bridging) | **Skip** | Adds a broker to run, secure, and patch. Its useful ideas (receive window, message expiry, session resume) are borrowed in rows 9–12. |
| 19 | gRPC bidirectional stream | **Skip** | Needs a separate HTTP/2 server next to Django and protobuf code generation. Pydantic DTOs plus JSON Schema already give a typed contract. |
| 20 | Multi-arch container image with host networking | **Adopt** | Publish `linux/amd64` and `linux/arm64` images built from `python:3.13-slim`. Document `network_mode: host`, since bridge networking doesn't deliver outside multicast. |
| 21 | `uv tool install` plus a hardened systemd unit on Raspberry Pi OS (Trixie, Python 3.13) | **Adopt** | Ship a sample unit with `DynamicUser=`, `StateDirectory=`, `ProtectSystem=strict`, and `NoNewPrivileges=`. |
| 22 | Single-file binary (PyInstaller, Nuitka, shiv) or prebuilt Pi image (Companion Satellite) | **Skip** | Builds per architecture because of C extensions such as `pydantic-core`, plus an image to keep patched. Too much upkeep for one maintainer. |
| 23 | Shared database and broker for every poller (LibreNMS distributed polling) | **Skip** | It requires each poller to reach the central DB and Redis, which is exactly what an isolated site can't do. |

## 1. Collector and proxy patterns

### Zabbix proxy

**Problem:** collect from a remote location over one TCP connection, without running trigger
evaluation or alerting there. Data is "stored locally before transmitting it over to the
server" ([docs](https://www.zabbix.com/documentation/current/en/manual/distributed_monitoring/proxies)).

- **Direction.** An *active* proxy (the default) connects to the server and requests its
  configuration. A *passive* proxy is connected to by the server. The default port is 10051. The
  configuration reference warns that with an active proxy "anyone can pretend to be an active
  proxy" unless encryption is configured
  ([config reference](https://www.zabbix.com/documentation/current/en/manual/appendix/config/zabbix_proxy)).
- **Buffering.** `ProxyOfflineBuffer` (default 1 h, up to 720 h) is how long data is kept while
  the server is unreachable. Older data is lost. `ProxyBufferMode` is `disk` (the default),
  `memory` (drops the oldest data when full, lost on shutdown), or `hybrid` (memory first, flush to
  the database when full, too old, or on shutdown) ([config reference](https://www.zabbix.com/documentation/current/en/manual/appendix/config/zabbix_proxy)).
- **Configuration sync.** The server is authoritative. Sync is incremental by revision number,
  with a full sync on proxy start or a failed update. Active proxies pull every
  `ProxyConfigFrequency` (default 10 s)
  ([sync](https://www.zabbix.com/documentation/current/en/manual/distributed_monitoring/proxies/sync)).
- **High availability.** Proxy groups let the server reassign hosts when a proxy goes offline
  ([HA](https://www.zabbix.com/documentation/current/en/manual/distributed_monitoring/proxies/ha)).
- **Trust.** Connections use TLS 1.2/1.3 with a PSK or certificates, and are unencrypted by
  default. PSKs are stored in the database in plain text
  ([encryption](https://www.zabbix.com/documentation/current/en/manual/encryption)). A PSK identity
  is up to 128 UTF-8 characters, sent in clear
  ([PSK](https://www.zabbix.com/documentation/current/en/manual/encryption/using_pre_shared_keys)).
- **Version skew.** Only a proxy of the same major version is fully compatible. An *outdated*
  proxy, no older than the previous LTS, still sends data and runs tasks but "cannot receive
  configuration updates". An *unsupported* proxy, older than that or newer than the server, is
  refused ([compatibility](https://www.zabbix.com/documentation/current/en/manual/appendix/compatibility)).
- **Packaging.** Docker images with SQLite or MySQL
  ([containers](https://www.zabbix.com/documentation/current/en/manual/installation/containers)).
- **License.** AGPL-3.0 from 7.0. Earlier versions are GPL-2.0
  ([license](https://www.zabbix.com/license)).

**For micboard:** adopt the active direction, the central-authoritative configuration with
revisions, a stated offline horizon, and the three skew tiers. The "outdated proxy still sends
data" rule is the right default: an old edge keeps reporting, but central doesn't send it targets
it can't understand.

### Prometheus agent mode and `remote_write`

**Problem:** scrape where the targets are, and push to remote storage without running queries
or a local TSDB.

- Agent mode (`--agent`) keeps scraping and service discovery. It drops local queries, alerting,
  and recording rules, and replaces the TSDB with a WAL. While the remote is unreachable, data
  stays on disk, but the buffer is "currently limited to two hours"
  ([agent mode](https://prometheus.io/docs/prometheus/latest/prometheus_agent/),
  [remote write practices](https://prometheus.io/docs/practices/remote_write/)).
- **Backpressure.** Each remote has a queue sharded from `min_shards` to `max_shards`. `capacity`
  is the number of samples per shard before WAL reading blocks, and one blocked shard blocks
  them all ([practices](https://prometheus.io/docs/practices/remote_write/),
  [configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)).
- **Remote-Write 2.0** (experimental, 2.0-rc.5). Payloads are Snappy-compressed protobuf, and the
  schema is selected by a `Content-Type` parameter plus an `X-Prometheus-Remote-Write-Version`
  header. A receiver answers 415 for an unsupported type, and the sender may fall back. Senders
  MUST retry 5xx with backoff, MAY retry 429 honouring `Retry-After`, and MUST NOT retry other 4xx.
  Receivers must handle duplicate requests idempotently
  ([spec](https://prometheus.io/docs/specs/prw/remote_write_spec_2_0/)).
- **Auth.** Basic, bearer, OAuth2, TLS client certificates, SigV4, and others
  ([configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)).
- **Federation** is the pull alternative: the parent scrapes `/federate` on the child, which needs
  inbound reachability ([federation](https://prometheus.io/docs/prometheus/latest/federation/)).
- **License.** Apache-2.0 ([LICENSE](https://github.com/prometheus/prometheus/blob/main/LICENSE)).

**For micboard:** adopt the retry rules and idempotent receive. Adapt content negotiation into a
schema version in the `hello` frame. Skip federation, because it needs the centre to reach the edge.

### OpenTelemetry Collector

**Problem:** a vendor-neutral pipeline of receivers, processors, and exporters that can run as
an *agent* next to the source or as a *gateway* per region
([configuration](https://opentelemetry.io/docs/collector/configuration/),
[agent](https://opentelemetry.io/docs/collector/deploy/agent/),
[gateway](https://opentelemetry.io/docs/collector/deploy/gateway/)).

- **Queueing.** `sending_queue` (default 1,000 entries) rejects new data when full unless
  `block_on_overflow` is set. Pointing `sending_queue.storage` at the `file_storage` extension
  makes the queue persistent across restarts. `retry_on_failure` backs off from 5 s to 30 s and
  gives up after 300 s by default
  ([exporterhelper](https://github.com/open-telemetry/opentelemetry-collector/blob/main/exporter/exporterhelper/README.md),
  [file_storage](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/extension/storage/filestorage/README.md)).
- **Backpressure.** `memory_limiter` returns errors upstream above a soft limit, so receivers
  push back on their sources
  ([memory_limiter](https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/memorylimiterprocessor/README.md)).
- **OTLP** over gRPC (4317) or HTTP (4318). It retries 429, 502, 503, and 504, honouring
  `Retry-After`, and never retries a partial success
  ([OTLP spec](https://opentelemetry.io/docs/specs/otlp/)).
- **OpAMP** (beta) manages a fleet of agents. The client connects to the server over WebSocket or
  polls over HTTP. It covers remote configuration with effective-config reporting, health,
  package updates, and "connection credentials management, including client-side TLS certificate
  revocation and rotation" ([OpAMP spec](https://opentelemetry.io/docs/specs/opamp/)).
- **License.** Apache-2.0
  ([LICENSE](https://github.com/open-telemetry/opentelemetry-collector/blob/main/LICENSE)).

**For micboard:** adapt OpAMP's shape (outbound WebSocket, config with an effective-config echo,
health reports, credential rotation over the same channel) without implementing OpAMP itself,
since its payloads are about telemetry agents, not device sessions. Adapt the bounded persistent
queue. Skip running the Collector itself: micboard's data is typed device state, not OTLP signals.

### Telegraf

**Problem:** a plugin-driven agent that "compiles into a standalone static binary" with no
external dependencies ([repo](https://github.com/influxdata/telegraf)).

- Each output buffers up to `metric_buffer_limit` (default 10,000) and overwrites the oldest when
  full. `buffer_strategy = "disk"` arrived in v1.32 as experimental, and a later issue reports
  the disk buffer stopping
  ([agent config](https://docs.influxdata.com/telegraf/v1/configuration/agent/),
  [v1.32.0](https://github.com/influxdata/telegraf/releases/tag/v1.32.0),
  [#16314](https://github.com/influxdata/telegraf/issues/16314)).
- Outputs include `http`, `mqtt` (MQTT 3.1.1/5, TLS client certs, QoS 0–2), and `websocket`
  ([outputs](https://github.com/influxdata/telegraf/tree/master/plugins/outputs),
  [mqtt output](https://github.com/influxdata/telegraf/blob/master/plugins/outputs/mqtt/README.md)).
- Builds for arm64 plus Debian and Alpine images
  ([install](https://docs.influxdata.com/telegraf/v1/install/)).
- **License.** MIT ([LICENSE](https://github.com/influxdata/telegraf/blob/master/LICENSE)).

**For micboard:** skip as a runtime. It can't hold vendor sessions under micboard's read-only
guard. Its "drop oldest" overflow rule is the one to borrow.

### Grafana Alloy

**Problem:** the successor to Grafana Agent (end of life 1 November 2025), a collector with
Prometheus and OpenTelemetry pipelines
([introduction](https://grafana.com/docs/alloy/latest/introduction/),
[FAQ](https://grafana.com/blog/grafana-agent-to-grafana-alloy-opentelemetry-collector-faq/)).

- **`remotecfg`.** Alloy polls a configuration URL (default every 1 min, minimum 10 s), sending an
  `id` and attributes. With no `id` it generates a UUID and stores it in `alloy_seed.json`. It
  supports bearer tokens and TLS client certificates
  ([remotecfg](https://grafana.com/docs/alloy/latest/reference/config-blocks/remotecfg/)).
- **Clustering** spreads scrape targets over peers by consistent hashing
  ([clustering](https://grafana.com/docs/alloy/latest/get-started/clustering/)).
- **WAL.** `prometheus.remote_write` keeps data for up to `max_keepalive_time` (8 h), then loses
  the oldest
  ([remote_write](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.remote_write/)).
- **License.** Apache-2.0 ([LICENSE](https://github.com/grafana/alloy/blob/main/LICENSE)).

**For micboard:** adopt the stable edge identity generated once and stored in the state
directory. Skip clustering. A segment needs one edge listener, because devices with a session
limit of 1 can't be shared between peers.

### Netdata parent and child streaming

**Problem:** children stream metrics to a parent that stores and serves them
([streaming](https://github.com/netdata/netdata/blob/master/src/streaming/README.md)).

- The child connects to the parent's `destination`, with `:SSL` for TLS. The parent authorizes
  by an API key (a UUID) or per machine GUID, with optional `allow from` patterns.
- The child keeps collecting while disconnected and reconnects after 5 s. On reconnect the parent
  replicates missed history (default up to 1 day). The child's send buffer is 10 MB, and if it
  fills, the child drops the connection, which leaves gaps.
- **Claiming to Netdata Cloud.** A space claim token is given by UI, file, or environment
  variable. The agent creates its own RSA key pair and connects outbound over WSS on 443.
  Regenerating the token "invalidates the previous token". Removing a node means deleting
  `cloud.d/` ([connect agent](https://learn.netdata.cloud/docs/netdata-cloud/connect-agent),
  [ACLK](https://learn.netdata.cloud/docs/netdata-cloud/agent-cloud-link-aclk)).
- **License.** GPL-3.0-or-later for the agent
  ([LICENSE](https://github.com/netdata/netdata/blob/master/LICENSE)).

**For micboard:** adopt claim-token enrolment and the outbound WSS link. Skip history
replication: micboard needs current state plus transitions, not a back-filled time series.

### Bitfocus Companion Satellite

**Problem:** connects control surfaces at a remote location to a central Companion, where they
appear as if they were attached locally ([repo](https://github.com/bitfocus/companion-satellite)).

- The satellite connects outbound to Companion on TCP 16622, or WebSocket 16623 since Companion
  3.5 ([repo](https://github.com/bitfocus/companion-satellite),
  [Satellite API](https://companion.free/for-developers/Satellite-API)).
- **Versioning.** Companion's greeting is `BEGIN CompanionVersion=… ApiVersion=…`, with a semver
  API version that the client checks. A table maps each API version to a minimum Companion
  release, and the stated policy is to "only ever add non-breaking functionality". Both sides
  PING and PONG, and the client pings every 2 s
  ([Satellite API](https://companion.free/for-developers/Satellite-API)).
- **Packaging.** An Electron desktop app, a prebuilt Raspberry Pi image, and a headless systemd
  service for x64 and arm64 Debian ([product page](https://companion.free/satellite/)).
- **Auth.** None documented in the sources read (*unverified*).
- **License.** MIT ([LICENSE](https://github.com/bitfocus/companion-satellite/blob/main/LICENSE)).

**For micboard:** adopt the greeting-with-version handshake and the additive-only rule. Adapt
the headless systemd route. Skip the prebuilt Pi image, and don't copy the absence of
authentication.

### LibreNMS distributed polling (counter-example)

All pollers "must connect to the same instance of" the database, RRDCached, and Redis, and the
feature is "not intended for remote polling"
([docs](https://docs.librenms.org/Extensions/Distributed-Poller/)). This is the model micboard's
Huey workers already follow inside one network, and why it doesn't extend to isolated sites.
**Skip.** License: GPL-3.0-or-later
([LICENSE](https://github.com/librenms/librenms/blob/master/LICENSE.txt)).

## 2. Crossing multicast boundaries

### What each vendor's discovery traffic can cross

| Traffic | Group and port | Scope | Can a router carry it? |
|---|---|---|---|
| mDNS / DNS-SD (Sennheiser `_ssc._udp`, `_ssc._tcp`) | `224.0.0.251:5353` | Link-local, "not forwarded off link" ([RFC 5771](https://www.rfc-editor.org/rfc/rfc5771.html)) | No. Only a reflector or proxy on the link. |
| Sennheiser MCP probe | `224.0.0.251:8133` | Link-local | No. |
| Shure discovery (SLP) | `239.255.254.253:8427` ([Shure group table](https://content-files.shure.com/KnowledgeBaseFiles/Dante_and_AES67_Multicast_Groups.pdf)) | IPv4 Local Scope `239.255.0.0/16` ([RFC 2365](https://www.rfc-editor.org/rfc/rfc2365.html)) | Only with multicast routing and a sender TTL above 1 (*unverified*). |
| Audio-Technica notifications and levels | `225.0.0.100:17000` by default, changeable with `snetw` ([A-T IP control spec](https://docs.audio-technica.com/us/wirelesssystem_ip_control_protocol_specifications_110_web_en_191217.pdf)) | IANA "reserved" block, which RFC 5771 says applications MUST NOT use | Technically routable, but scope undefined and sender TTL not published (*unverified*). |

On Linux, `IP_MULTICAST_TTL` defaults to 1
([man page](https://man7.org/linux/man-pages/man2/IP_MULTICAST_TTL.2const.html)), and the
smcroute README notes that most stacks do the same
([smcroute](https://github.com/troglobit/smcroute)). The TTL each device uses must be measured
with a packet capture before relaying is even considered.

### mDNS reflectors and discovery proxies

- **RFC 6762** says `.local` names "are meaningful only on the link where they originate".
  Responses SHOULD use IP TTL 255, and responders SHOULD ignore unicast queries from off-link
  sources ([RFC 6762](https://www.rfc-editor.org/rfc/rfc6762.html), sections 5.5, 11).
- **Avahi** `enable-reflector` (default off) reflects mDNS between all local interfaces. The man
  page warns against running more than one reflector between the same networks, because packets
  bounce between them. `reflect-filters` limits reflection to listed service types
  ([avahi-daemon.conf](https://github.com/avahi/avahi/blob/master/man/avahi-daemon.conf.5.xml.in)).
  License: LGPL-2.1 ([LICENSE](https://github.com/avahi/avahi/blob/master/LICENSE)).
- **mdns-repeater** repeats mDNS between interfaces. GPL-2.0-or-later
  ([repo](https://github.com/geekman/mdns-repeater)).
- **RFC 8766 Discovery Proxy** answers unicast DNS for a delegated subdomain by issuing mDNS
  queries on its own link, only on demand. It "does not operate as a multicast relay or multicast
  forwarder", so it can't loop, and it MUST rate-limit the multicast it generates. Its security
  section warns that exposing link services leaks information
  ([RFC 8766](https://www.rfc-editor.org/rfc/rfc8766.html)). DNS Push
  ([RFC 8765](https://www.rfc-editor.org/rfc/rfc8765.html)) and Service Registration Protocol
  ([RFC 9665](https://www.rfc-editor.org/rfc/rfc9665.html)) complete the unicast picture. An mDNS
  relay to a central proxy is still a draft
  ([draft-ietf-dnssd-mdns-relay](https://datatracker.ietf.org/doc/draft-ietf-dnssd-mdns-relay/)).
- **Security.** CERT VU#550620 found that mDNS responders answering off-link queries leak device
  information and can amplify denial of service ([VU#550620](https://www.kb.cert.org/vuls/id/550620)).
- **Python.** `python-zeroconf` is LGPL-2.1-or-later and has native asyncio classes
  (`AsyncZeroconf`, `AsyncServiceBrowser`)
  ([repo](https://github.com/python-zeroconf/python-zeroconf),
  [API](https://python-zeroconf.readthedocs.io/en/latest/api.html)).

### SLP directory agents

RFC 2608 defines User, Service, and Directory Agents. A Directory Agent is reached by unicast, so
it works across routers. Agents find it by multicast to `239.255.255.253:427`, by static
configuration, or by DHCP options 78 and 79
([RFC 2608](https://www.rfc-editor.org/rfc/rfc2608.html),
[RFC 2610](https://www.rfc-editor.org/rfc/rfc2610.html)). Shure's discovery uses a different
group and port, and the open-source micboard simply joins `239.255.254.253:8427` and parses a
device ID from the payload ([discover.py](https://github.com/karlcswanson/micboard/blob/master/py/discover.py),
MIT). No evidence was found that Shure devices register with a DA (*unverified*). OpenSLP is
BSD-licensed and its last release was 2.0.0 in 2019 ([SourceForge](https://sourceforge.net/projects/openslp/)).

### IGMP proxying

RFC 4605 forwards multicast down a tree from one upstream interface without PIM. It has no loop
detection and stays inside one administrative domain
([RFC 4605](https://www.rfc-editor.org/rfc/rfc4605.html)). Implementations: `igmpproxy`
(GPL-2.0-or-later, [repo](https://github.com/pali/igmpproxy)) and `smcroute` (GPL-2.0). Neither
helps link-local groups.

### Vendor guidance

- Shure Wireless Workbench's troubleshooting page requires the computer to be "on the same subnet
  as the device" ([WWB](https://content-files.shure.com/Pubs/WWB/en-US/en-US/network-troubleshooting.html)).
  Shure knowledge-base articles describe adding some product lines by IP from another subnet, but
  could not be fetched directly (*unverified*).
- Sennheiser says the Control Cockpit mDNS port can be disabled and devices "added manually
  instead" ([network ports](https://docs.cloud.sennheiser.com/en-us/tc-bar/tc-bar/security-white-paper/network-ports.html)).
  SSC clients "SHOULD NOT rely on default ports" and must take the port from the SRV record
  ([SSC developer guide](https://www.sennheiser.com/globalassets/digizuite/41931-en-ti_1109_v2.2_sennheiser_sound_control_protocol_digital_6000_en.pdf)).
- Audio-Technica allows one TCP control connection at a time on port 17300. Live state changes
  and 100 ms level updates arrive on the multicast group
  ([A-T IP control spec](https://docs.audio-technica.com/us/wirelesssystem_ip_control_protocol_specifications_110_web_en_191217.pdf)).
- Dante Domain Manager, the nearest industry analogue, crosses subnets with unicast DNS-SD records
  in the DHCP search domain. Without DNS, it falls back to static IP enrolment
  ([DDM bootstrapping](https://dev.audinate.com/GA/ddm/userguide/webhelp/content/bootstrapping_dante_devices.htm)).

### When to relay discovery and when to collect locally

**Run an edge listener in the segment when any of these hold:**

- the segment is isolated by policy;
- central has no unicast route to the devices;
- discovery uses a link-local group, or the sender's TTL is 1;
- state arrives on multicast (Audio-Technica levels), which a local listener can read passively
  without taking the device's single TCP slot;
- a single-session device should keep its session close to it, so a WAN outage doesn't drop and
  re-establish the session.

**Add devices by IP on central, with no edge and no relay, when** unicast routing to the devices
already exists and policy allows it. Discovery is a convenience. The session is what matters.

**Relay discovery only when** the segments are trusted and already routed, a single reflector is
filtered to the needed service types, and only the initial address is needed. micboard should
document this for operators but never depend on it.

## 3. Edge-to-central transport

### Outbound only, through NAT

RFC 5382 requires NATs to keep an established TCP mapping idle for at least 2 h 4 min
([RFC 5382](https://www.rfc-editor.org/rfc/rfc5382.html)), and RFC 4787 sets 2 min for UDP
([RFC 4787](https://www.rfc-editor.org/rfc/rfc4787.html)). Proxies are far less patient: the
`websockets` documentation cites about 30 s of silence before some proxies cut a connection, and
TCP keepalive (2 h or more) is no substitute
([keepalive](https://websockets.readthedocs.io/en/stable/topics/keepalive.html)). So a
long-lived edge connection needs application-level pings every 20–30 s.

### Options compared

| Transport | Fit | Notes |
|---|---|---|
| **WebSocket (WSS)** | **Adopt** | Already in the stack: `channels` (BSD-3-Clause, [LICENSE](https://github.com/django/channels/blob/main/LICENSE)) serves it, and `websockets` (BSD-3-Clause, [LICENSE](https://github.com/python-websockets/websockets/blob/main/LICENSE)) is the client. The client defaults to 20 s pings, a 1 MiB message cap, write-side backpressure, and reconnect with jittered exponential backoff capped at 60 s ([client API](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html)). Close codes 4000–4999 are free for applications ([RFC 6455 §7.4.2](https://www.rfc-editor.org/rfc/rfc6455#section-7.4.2)). Netdata's ACLK, OpAMP, and Companion Satellite all use it. |
| **HTTPS push** | **Adapt** (enrolment only) | Stateless and works through any proxy. Backpressure is 429/503 with `Retry-After` ([RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585#section-4), [RFC 9110 §10.2.3](https://httpwg.org/specs/rfc9110.html#field.retry-after)). Central-to-edge configuration would need polling, as Alloy `remotecfg` does. Use it for the one-time token exchange. |
| **MQTT 5** | **Skip** | Good flow control (Receive Maximum), session expiry, and message expiry ([MQTT 5.0](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html)), but it needs a broker. Mosquitto is EPL-2.0 or BSD-3-Clause ([LICENSE](https://github.com/eclipse-mosquitto/mosquitto/blob/master/LICENSE.txt)), and aiomqtt is BSD-3-Clause ([LICENSE](https://github.com/empicano/aiomqtt/blob/main/LICENSE)). |
| **gRPC** | **Skip** | Bidirectional streams with HTTP/2 flow control ([flow control](https://grpc.io/docs/guides/flow-control/)). Client keepalive is off by default, and the server sends GOAWAY if clients ping too often, so both ends must be tuned ([keepalive](https://grpc.io/docs/guides/keepalive/)). Apache-2.0 ([LICENSE](https://github.com/grpc/grpc/blob/master/LICENSE)). Needs a second server beside Django. |

### Store and forward, backpressure, and schema skew

- **Outbox.** SQLite in WAL mode with `synchronous=FULL` survives power loss, and WAL doesn't
  work on network filesystems ([SQLite WAL](https://www.sqlite.org/wal.html)). Huey's
  `SqliteHuey` uses the stdlib `sqlite3` with an optional `fsync`
  ([Huey API](https://huey.readthedocs.io/en/latest/api.html), MIT), so it is available on the
  edge without a new dependency. A plain outbox table is simpler still, because frames are
  ordered and acknowledged by sequence, which a task queue doesn't model.
- **What to keep.** micboard broadcasts state, and ADR-016 already skips unchanged DTOs. During an
  outage, the edge keeps only the latest normalized DTO per target. Online and offline
  transitions, alerts, and discovery events go to the durable outbox, bounded by age (default 1 h,
  matching Zabbix) and size, dropping the oldest. On reconnect it sends transitions in order, then
  one snapshot per target.
- **Backpressure.** Central acknowledges frames by `seq`. The edge stops sending past an in-flight
  window (like MQTT's Receive Maximum) and coalesces while it waits. The `websockets` send call
  already blocks when its write buffer is full.
- **Idempotency.** Central keeps a high-water mark per edge and ignores any `seq` at or below it.
  This is the same duty Remote-Write 2.0 places on receivers.
- **Schema.** Pydantic v2 `extra="ignore"` lets central accept newer additive fields, and
  `extra="forbid"` in tests catches drift
  ([config](https://pydantic.dev/docs/validation/latest/api/pydantic/config/)).
  `model_json_schema()` publishes the frame schema as JSON Schema 2020-12 for a contract test
  ([JSON Schema](https://pydantic.dev/docs/validation/latest/concepts/json_schema/)). The `hello`
  frame carries the semver schema version, and skew follows Zabbix's tiers.

## 4. Enrolment and trust

| Approach (source) | How it works | License | Verdict |
|---|---|---|---|
| Kubernetes bootstrap tokens and kubelet TLS bootstrap ([tokens](https://kubernetes.io/docs/reference/access-authn-authz/bootstrap-tokens/), [kubelet](https://kubernetes.io/docs/reference/access-authn-authz/kubelet-tls-bootstrapping/)) | A token `[a-z0-9]{6}.[a-z0-9]{16}` (public ID plus secret) with an expiry is used once to get a signed client certificate, which then rotates itself. | Apache-2.0 | **Adopt** the token format and the exchange. **Skip** the certificate. |
| Netdata claim token ([connect agent](https://learn.netdata.cloud/docs/netdata-cloud/connect-agent)) | The token is given by environment variable or file, and regenerating it invalidates the old one. | GPL-3.0-or-later | **Adopt** environment-variable enrolment. |
| Zabbix PSK ([PSK](https://www.zabbix.com/documentation/current/en/manual/encryption/using_pre_shared_keys)) | Long-lived shared key per proxy, stored in plain text on the server. | AGPL-3.0 | **Skip**: stored unhashed. |
| django-rest-knox ([settings](https://github.com/jazzband/django-rest-knox/blob/develop/docs/settings.md)) | Tokens stored hashed (SHA-512), with an optional TTL, and deleting the row revokes. | MIT | **Adapt**: Knox tokens belong to a user, so an edge would need a service user. A small edge credential model with the same hashing is cleaner. |
| smallstep step-ca ([provisioners](https://smallstep.com/docs/step-ca/provisioners/), [revocation](https://smallstep.com/docs/step-ca/revocation/)) | One-time tokens or ACME for short-lived certificates. Revocation is passive: a revoked certificate can't renew and expires. | Apache-2.0 | **Skip for now**. Revisit if mTLS is ever required. |
| SPIFFE/SPIRE join tokens ([configuring](https://spiffe.io/docs/latest/deploying/configuring/)) | Single-use join token, then automatically rotated SVIDs. | Apache-2.0 | **Skip**: a whole identity platform. |
| Tailscale and headscale auth keys ([Tailscale](https://tailscale.com/kb/1085/auth-keys), [headscale](https://headscale.net/stable/ref/registration/)) | Pre-authorized, optionally ephemeral keys that join a node to an overlay network. | BSD-3-Clause | **Skip** as a dependency. Operators may still use one. |
| mTLS at nginx ([ssl module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)) | `ssl_verify_client` with a CA and CRL, passing the certificate to the app in a header. | BSD-2-Clause | **Skip for now**: a CA, a CRL, and trusted-header plumbing. |

**micboard's flow:**

1. An admin creates an edge listener and assigns it a location. Central shows a single-use
   enrolment token once, valid for 1 h. Only its hash is stored.
2. The edge starts with the token in an environment variable, generates its own `edge_id` once
   (as Alloy does), and POSTs the token over HTTPS.
3. Central marks the token used and returns a random 256-bit credential, stored hashed and never
   shown again (ADR-016 clause 7). A high-entropy secret makes a fast hash such as SHA-256
   sufficient.
4. The edge stores the credential in its state directory with mode `0600` and opens the WSS
   connection with it in the `Authorization` header.
5. **Rotation.** Central can send a new credential over the open connection. The old one stays
   valid for a short grace period, until the edge acknowledges.
6. **Revocation.** Deleting or disabling the edge deletes the credential and closes any open
   socket with a "revoked" close code. The edge stops reconnecting and logs once.

## 5. Packaging

- **Container.** `docker buildx` builds multi-platform images
  ([multi-platform](https://docs.docker.com/build/building/multi-platform/)), and the official
  `python:3.13-slim` image covers amd64 and arm64 ([python image](https://hub.docker.com/_/python)).
  Bridge networking doesn't deliver multicast from outside the host
  ([moby#3043](https://github.com/moby/moby/issues/3043)). The edge needs host networking
  ([host driver](https://docs.docker.com/engine/network/drivers/host/)) or macvlan, where the
  container can't reach the host and the switch must allow promiscuous mode
  ([macvlan](https://docs.docker.com/engine/network/drivers/macvlan/)).
- **Raspberry Pi.** Raspberry Pi OS is now based on Debian Trixie
  ([OS docs](https://www.raspberrypi.com/documentation/computers/os.html)), which ships Python
  3.13 ([Debian package](https://packages.debian.org/trixie/python3)). PEP 668 blocks system-wide
  installs, which `uv tool install` sidesteps with an isolated environment
  ([uv tools](https://docs.astral.sh/uv/guides/tools/)). uv supports Linux aarch64 at Tier 2
  ([platforms](https://docs.astral.sh/uv/reference/policies/platforms/)).
- **systemd.** `DynamicUser=`, `StateDirectory=` (for the outbox and credential),
  `ProtectSystem=strict`, `ProtectHome=`, `PrivateTmp=`, and `NoNewPrivileges=` harden the unit
  without a hand-made user ([systemd.exec](https://man7.org/linux/man-pages/man5/systemd.exec.5.html)).
- **Single binary.** PyInstaller is GPL-2.0-or-later with a bootloader exception
  ([COPYING](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)), Nuitka is now
  AGPL-3.0-or-later with a runtime exception ([PyPI](https://pypi.org/project/Nuitka/)), and shiv
  builds per-architecture zipapps ([shiv](https://github.com/linkedin/shiv)). The stdlib `zipapp`
  can't load C extensions from the archive ([zipapp](https://docs.python.org/3/library/zipapp.html)),
  and `pydantic-core` is one. Each would be another per-architecture build to maintain. **Skip.**

## Recommended reference architecture

```text
 Site or segment A (isolated VLAN)                          Central micboard
+----------------------------------------------+          +-------------------------------------+
| edge listener  (same micboard package,       |          |  Django + Channels (ASGI)           |
|                 "edge" settings profile)     |          |                                     |
|                                              |          |  /edge/enrol   HTTPS POST, one-time |
|  discovery service                           |          |                token -> credential  |
|   - mDNS/DNS-SD _ssc  (224.0.0.251)          |          |                                     |
|   - Sennheiser MCP probe (224.0.0.251:8133)  |          |  /edge/ws      WSS consumer         |
|   - Shure SLP listen (239.255.254.253:8427)  |          |   - auth: hashed edge credential    |
|   - A-T group listen (225.0.0.100:17000)     |          |   - hello: edge_id, schema semver   |
|        |                                     |          |   - ack by seq, high-water mark     |
|        v                                     |          |   - close 4xxx: revoked / skew      |
|  realtime process (stdlib asyncio)           |          |           |                         |
|   - device sessions: TCP, UDP, Ember+, HTTP  |  outbound|           v                         |
|   - read-only guard in every transport       |  WSS only|  edge ingest service                |
|   - session semaphore, DB-backed backoff     |  (pings  |   - validate frame DTOs (pydantic)  |
|        |  normalized DTOs                    |   20 s)  |   - same chassis lifecycle and      |
|        v                                     | -------> |     broadcast path as local devices |
|  edge outbox (SQLite, WAL)                   |          |           |                         |
|   - latest DTO per target (coalesced)        | <------- |           v                         |
|   - transitions/alerts, bounded 1 h, FIFO    | config   |  PostgreSQL, Huey, Channels groups  |
|   - seq numbers, in-flight window            | rev N,   |  (browsers, API, alerts)            |
|                                              | rotate,  |                                     |
|  allowlist scrubber on all diagnostics       | refresh  |  admin: create edge, show token,    |
+----------------------------------------------+          |  assign targets, revoke             |
                                                          +-------------------------------------+
 Site or segment B: another edge listener, same shape
 Routed segments with no edge: central's own realtime process and Huey, devices added by IP
```

**Rationale.**

- **Collect, don't relay.** Discovery groups are link-local or non-conformant, and every vendor
  session needs reachability anyway. Audio-Technica puts live state on multicast and allows one
  control client, so a local listener reads it passively.
- **Same code, different profile.** The edge runs micboard's own discovery service, realtime
  process, read-only guard, session semaphore, and DB-backed backoff (ADR-015, ADR-016) against a
  local SQLite database. Central treats its own realtime process as the implicit edge for routed
  segments, so there is one code path, not two.
- **One outbound WSS connection** reuses `channels` and `websockets`, which are already
  dependencies. It carries telemetry up and configuration, credential rotation, and debounced
  "refresh now" down. It never carries device writes. The read-only guard stays at the edge, next
  to the transports, and central has no command channel that could reach hardware.
- **Bounded, coalescing buffer.** micboard needs current state and transitions, not a back-filled
  time series. So the outbox is small and its loss horizon is explicit.
- **Low maintenance.** No broker, no CA, no VPN, no second server, and no per-architecture binary.
  It ships as one multi-arch image and one systemd unit.

**Open points** for the design ticket that follows this research:

- whether the edge runs Huey at all, or polls stateless HTTP devices from the realtime process;
- the exact WSS frame schema and close codes;
- whether an edge listener is a new model or an attribute of an existing location;
- measuring the IP TTL each vendor's discovery traffic uses, with a packet capture on real
  hardware.
