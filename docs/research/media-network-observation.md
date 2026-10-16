---
title: "Research: Passive Observation of Dante, AES67, and ST 2110 Media Networks"
---
**Question** ([#376](https://github.com/justprosound/django-micboard/issues/376), part of
[#321](https://github.com/justprosound/django-micboard/issues/321)): how can micboard
**passively** monitor Dante, AES67, and SMPTE ST 2110 media networks from inside an isolated
segment, with an Edge Listener that never bridges media traffic out
([#375](https://github.com/justprosound/django-micboard/issues/375))?

**Date:** 2026-10-16. All sources are public. IEEE 1588, AES67, and the SMPTE ST 2059 and
ST 2110 documents are paywalled, so their parameters are taken from public summaries, vendor
documentation, and open-source implementations, and are labelled as such. Claims marked
*unverified* could not be confirmed from a primary source and should be measured on hardware
before a design depends on them.

**Constraints carried in from earlier decisions:**

- One **segment collector** per isolated segment, in its own Linux network namespace on a VLAN
  sub-interface. It never forwards, bridges, routes, or reflects traffic between segments (#375).
- Collectors pass normalized, scrubbed DTOs to the uplink over a Unix socket. Only the uplink
  opens the outbound WSS to central. Raw packets, pcaps, and SDP bodies with internal addressing
  never leave the segment (#375, item 6).
- Every transport has a default-deny read-only guard, and every write exception is named
  (ADR-016 clause 12).
- Capabilities are `typing.Protocol`s, and Device Manager topology is vendor-neutral (ADR-015).
- Alerts are evaluated centrally from reported facts (#366).

## Summary

1. **Most of what matters is observable without sending a packet.**
   - PTP Announce messages carry the grandmaster's identity, priorities, clock class, accuracy,
     variance, time source, and steps removed.
   - SAP announcements carry complete SDP for AES67 and ST 2110-30 flows, including the PTP
     grandmaster and domain each flow is locked to (RFC 7273 `ts-refclk`).
   - Dante devices announce themselves over mDNS and send multicast heartbeats with clock and
     receive-health records.
2. **Some facts need a query.** Each query below is read-only if the guard pins it to an exact
   form:
   - RTSP `DESCRIBE` for RAVENNA SDP;
   - NMOS IS-04 Query API `GET`s;
   - IS-05 `GET .../transportfile`;
   - IS-12 `Get` commands for BCP-008 receiver status;
   - Dante Managed API GraphQL `query` operations;
   - PTP management `GET` through ptp4l's read-only socket.
3. **A PTP slave's offset is not passively observable.** A passive observer sees the
   grandmaster's view only. Per-device offset and lock state come from:
   - the device itself (BCP-008, the Dante Managed API, and Dante heartbeats);
   - or an opt-in probe clock that the collector runs.
4. **RTP loss needs an IGMP join, and a join pulls traffic onto the trunk.** Audio flows are
   cheap: about 3–80 Mbit/s each. A single ST 2110-20 video flow is gigabits. So joins are
   budgeted, audio-only, classified from SDP, and watched by a rate watchdog. **Video essence
   is never joined.**
5. **Licenses are workable.**
   - linuxptp is **GPL-2.0-or-later**, not GPL-2.0-only. Its source headers say so.
     Run it as an external process anyway.
   - Scapy is **GPL-2.0-only** and must not be imported.
   - nmos-cpp and the AMWA specs are Apache-2.0, and netaudio is the Unlicense.
   - The Dante Managed API is proprietary but free with a DDM licence, and it is only called
     over HTTP.
6. **It belongs inside micboard as a sibling product area,** "media network monitoring." It
   shares the Edge Listener, tenancy, alerting, and Device Manager topology, but adds its own
   device kinds and vocabulary rather than stretching the RF ones.

## Recommendations

| # | Item | Verdict | Concrete change to micboard |
|---|---|---|---|
| 1 | Passive PTP Announce/Sync observation, v1 and v2 (IEEE 1588-2002/2008/2019) | **Adopt** | The segment collector joins `224.0.1.129` (ports 319/320) and parses headers and Announce bodies with a small in-house `struct` parser. It reports a **PTP Domain** observation per domain number. |
| 2 | linuxptp `ptp4l` + `pmc` (GPL-2.0-or-later) | **Adapt** | An optional, opt-in **probe clock**: `ptp4l` with `clientOnly 1` and `free_running 1` as an external process. It is read through `pmc` on the `uds_ro_address` socket, which accepts only GET. It sends Delay_Req, so it needs a named ADR-016 exception. Off by default. |
| 3 | PTP management GET to devices over the network | **Skip for now** | Device support is unknown (*unverified*), and the same message type carries SET and COMMAND. Revisit after captures. |
| 4 | SAP/SDP listener (RFC 2974, RFC 8866) | **Adopt** | Listen on `239.255.255.255:9875` and keep a session cache keyed by SDP origin. It yields the **Media Flow** inventory, `ts-refclk` linkage, and "flow withdrawn" and "announcement stale" facts. |
| 5 | RAVENNA DNS-SD + RTSP `DESCRIBE` | **Adopt** | Browse `_ravenna._sub._rtsp._tcp` and `_ravenna_session` subtypes. Fetch SDP with `DESCRIBE` only. The guard denies `SETUP`, `PLAY`, `ANNOUNCE`, and `SET_PARAMETER`. |
| 6 | AMWA NMOS IS-04 Query API (read-only use of an existing registry) | **Adopt** | An NMOS plugin with Device Manager topology: `GET` resources, plus one named exception for `POST /subscriptions` with `persist: false`. It never touches the Registration API. |
| 7 | AMWA IS-05 | **Adapt** | `GET /single/senders/{id}/transportfile` and `/active` only. `PATCH /staged` is denied. |
| 8 | AMWA BCP-008-01/-02 over IS-12 | **Adapt (later)** | Read `NcReceiverMonitor` status properties and lost or late packet counters with `Get` commands, plus event `Subscription` messages. `Set` and `ResetCountersAndMessages` are denied. |
| 9 | nmos-cpp (Apache-2.0) | **Adopt as a test fixture** | Run its registry container in CI as the IS-04/IS-05 target. Don't link or vendor it. |
| 10 | Dante mDNS (`_netaudio-arc`, `-chan`, `-cmc`, `-dbc` `._udp`) and heartbeats (`224.0.0.233:8708`) | **Adopt** | A Dante plugin (direct topology, unverified tier) that listens only. It feeds **Media Endpoint** inventory, online/offline state, and device clock and receive-health records. |
| 11 | Dante control-port queries (UDP 4440/8800, reverse engineered) | **Skip** | The opcode space mixes reads and writes and is undocumented. Reconsider only with captured fixtures and an exact opcode allowlist. |
| 12 | Dante Managed API (GraphQL, DDM 1.5+ and Dante Director) | **Adapt** | A Device Manager connection that sends only `query` operations, checked by parsing the document with graphql-core (MIT). It polls, because the schema has no GraphQL `Subscription` type. Use an API key from a dedicated low-privilege user. |
| 13 | netaudio / network-audio-controller (Unlicense) | **Adapt as reference** | Use it as documentation for heartbeat and mDNS formats. Don't depend on it: it is a full controller with write paths. |
| 14 | Inferno (GPL-3.0-or-later or AGPL-3.0-or-later) | **Skip at runtime** | It is a Dante endpoint emulator, not a monitor. It is a possible source of hand-written fixtures. |
| 15 | RTP sequence and loss probe on audio flows (RFC 3550) | **Adapt** | A budgeted **Flow Probe**: audio-only, SDP-classified, time-boxed joins with a per-host Mbit/s budget and a rate watchdog. Prefer receiver-reported loss (BCP-008, Dante heartbeats) when available. |
| 16 | Joining ST 2110-20 video (or -22, -40) | **Never** | Denied by classification, by a bitrate cap, and by the watchdog. |
| 17 | Scapy (GPL-2.0-only) | **Skip** | It can't be combined with AGPL-3.0-or-later code. Use `struct` parsers. |
| 18 | Wireshark/tshark, EBU LIST (pi-list) | **Skip at runtime** | They are developer tools for capturing and inspecting fixtures. LIST analyses full essence captures, including video. |

## 1. Clocks: PTP

### 1.1 What the wire carries

PTP event messages (Sync, Delay_Req) use UDP port 319 and general messages (Announce,
Follow_Up, Delay_Resp, Management) use port 320, on `224.0.1.129` for the default domain. Audinate
lists PTP on `224.0.1.129`–`224.0.1.132`, ports 319/320, for Dante networks
([Audinate, *DDM Information for Network Administrators* v1.11, §3.1][ddm-netadmin]).

The Announce body, as laid out in linuxptp's `msg.h` (public reference for the IEEE 1588 layout;
read for facts, not copied) ([linuxptp `msg.h`][lptp-msg]):

| Field | What a passive observer learns |
|---|---|
| header `domainNumber`, `versionPTP`, `sourcePortIdentity`, `logMessageInterval`, `flags` (two-step) | which domain and version; who is sending; the announce rate; whether Follow_Up is used |
| `grandmasterIdentity` (EUI-64 clock identity) | **the current grandmaster** |
| `grandmasterPriority1`, `grandmasterPriority2` | BMCA priorities |
| `grandmasterClockQuality` = `clockClass`, `clockAccuracy`, `offsetScaledLogVariance` | lock state of the grandmaster, for example a clock class indicating traceable lock versus holdover or free-run |
| `timeSource` | GPS, PTP, internal oscillator, and so on |
| `stepsRemoved` | how many boundary clocks sit between the grandmaster and this segment |
| `currentUtcOffset` | the TAI-UTC offset in use |

From the stream of Announce and Sync messages, without sending anything, a collector can also
derive:

- **BMCA changes:** the grandmaster identity changed, or Announce from a new master appeared.
- **No grandmaster:** no Announce within `announceReceiptTimeout` × the announce interval.
- **Competing masters:** two different `sourcePortIdentity` values sending Announce in the same
  domain over a sustained window, which points to a partition or misconfiguration.
- **Sync regularity:** gaps in Sync `sequenceId` and the inter-arrival distribution against the
  advertised `logMessageInterval`.
- **Transparent clocks present:** a non-zero `correctionField`.
- **Who follows the grandmaster:** in end-to-end mode, followers send Delay_Req to the
  multicast group, so their `sourcePortIdentity` reveals them. This gives a passive list of PTP
  followers per domain.

**What it cannot learn passively:** any follower's offset from the master, or its servo lock
state. Those values exist only inside the follower. Reading them needs the device's own
reporting (§3, §2.3) or a management GET (§1.4).

### 1.2 Versions and profiles

- **IEEE 1588-2002 (PTPv1).** Dante uses PTPv1 for its own clocking. The Dante Managed API
  schema has a `DeviceClockingPTPV1UnicastDelayRequestSet` mutation
  ([Dante Managed API User Guide v1.8, Appendix 1][dante-mapi]). PTPv1 shares the ports and
  group, but the message format differs, so the parser branches on the version nibble.
- **IEEE 1588-2008 (PTPv2)** and **IEEE 1588-2019 (v2.1).** v2.1 keeps the v2 wire format and adds
  `minorVersionPTP`. One parser covers both.
- **Profile defaults** (log2 seconds), from vendor profile tables because the AES and SMPTE texts
  are paywalled ([Juniper, *PTP media profiles*][juniper-ptp]):

| Parameter | AES67 media profile | SMPTE ST 2059-2 |
|---|---|---|
| Domain | 0 (0–127) | 127 (0–127) |
| Announce interval | 1 (0 to 4) | −2 (−3 to 1) |
| Announce receipt timeout | 3 | 3 |
| Sync interval | −3 (−4 to 1) | −3 (−7 to −1) |
| Delay_Req interval | −3 | −3 |

RAVENNA nodes must support PTPv2 slave operation with a configurable domain, default 0
([RAVENNA Operating Principles, §3.2][ravenna-op]).

**Design consequence:** the collector reports `domain_number`, `ptp_version`, and the observed
intervals, and guesses the profile from them (`aes67`, `st2059_2`, `dante_v1`, `default`,
`unknown`). The "no grandmaster" timeout uses the *observed* announce interval × the observed
or default receipt timeout, never a hard-coded one.

### 1.3 Tools and licenses

| Tool | License (primary source) | Use |
|---|---|---|
| linuxptp `ptp4l`, `pmc` | **GPL-2.0-or-later**. `ptp4l.c` and `pmc.c` say "either version 2 of the License, or (at your option) any later version", and newer files carry `SPDX-License-Identifier: GPL-2.0+` ([`pmc.c`][lptp-pmc], [`monitor.c`][lptp-monitor]). `COPYING` is the GPLv2 text, which is why GitHub shows "GPL-2.0". | Run as an **external process** inside the segment namespace. Never copy code. "Or later" makes it legally compatible with AGPL-3.0-or-later. Process separation still keeps the boundary obvious and lets the image ship it as an aggregate. |
| Wireshark dissectors | GPL-2.0, per GitHub detection ([repo][wireshark]) | Developer reference and fixture inspection only. |

Useful linuxptp features, all from the `ptp4l(8)` man page ([`ptp4l.8`][lptp-man]):

- `free_running 1`: "Don't adjust the local clock if enabled. The measured offset and frequency
  will be printed." The probe measures without steering the host clock.
- `uds_ro_address`: "restricted to GET actions and does not forward messages to other ports.
  Access to this socket can be given to untrusted applications for monitoring purposes." This
  is a read-only guard by construction, so micboard's `pmc` calls go to this socket only.
- `slave_event_monitor`: a UNIX socket that receives `SLAVE_RX_SYNC_TIMING_DATA` and
  `SLAVE_DELAY_TIMING_DATA_NP` TLVs, giving per-Sync timing without polling.
- `clientOnly 1`: the port never enters the master state, so the probe can't win the BMCA.

### 1.4 What is read-only

| Action | Sends packets? | Changes device state? | Verdict |
|---|---|---|---|
| Listening to Announce, Sync, Follow_Up, Delay_Req, and Delay_Resp | IGMP join only | No | Allowed |
| Probe clock (`ptp4l clientOnly free_running`) | Delay_Req to the master | No. The master answers with Delay_Resp, and its BMCA ignores a client-only port. | **Named ADR-016 exception**, opt-in per segment, off by default |
| `pmc` to the local `ptp4l` over `uds_ro_address` | No network traffic | No | Allowed |
| PTP Management GET to devices (`pmc -b`) | Yes | No for GET, **yes for SET and COMMAND** (`tlv.h` defines GET, SET, RESPONSE, COMMAND) ([`tlv.h`][lptp-tlv]) | Skip until device support is captured. If added, the guard admits `actionField == GET` with an allowlisted `managementId` (`CURRENT_DATA_SET`, `PARENT_DATA_SET`, `TIME_STATUS_NP`) only. |

Hardware timestamping on a VLAN sub-interface or a macvlan inside a namespace depends on the
NIC driver (*unverified*). Without it, the probe's offset numbers are software-timestamped and
good only for detecting large steps. The probe reports its timestamping mode so central can
discount it.

## 2. Stream inventory

### 2.1 SAP and SDP (AES67, ST 2110-30, Dante's AES67 mode)

- **Where:** SAP announcements "MUST be sent on port 9875", on the highest address of the
  administrative scope zone. For `239.255.0.0/16` that is `239.255.255.255`
  ([RFC 2974 §3][rfc2974]). Audinate lists "SAP/SDP is on 239.255.255.255:9875/UDP" and "RTP
  audio is on 239.69/16:5004/UDP (address is configurable)" for AES67 and SMPTE ST 2110-30
  ([DDM network admin §3.3][ddm-netadmin]). netaudio uses the same constants
  ([`_protocols.py`][nac-protocols]).
- **Status:** SAP is Experimental (RFC 2974). SDP is RFC 8866, which obsoletes RFC 4566
  ([RFC 8866][rfc8866]).
- **Timing:** the base interval is `max(300 s, 8 × ads × size / 4000 bit/s)`, with ±⅓ jitter.
  A session is dropped from the cache only after "ten times the announcement period, or one
  hour, whichever is the greater", or on an explicit deletion packet ([RFC 2974 §3.1, §4][rfc2974]).
  AES67 devices are commonly configured to announce much faster than every 300 s
  (*unverified*), so the collector **learns each origin's interval** rather than assuming one.
- **What the SDP gives, with no query:**
  - `m=` media kind and port;
  - `a=rtpmap` encoding, rate, and channels (`L24/48000/8`, `L16`, `AM824`);
  - `a=ptime` packet time;
  - `c=` group address and `a=source-filter` (RFC 4570);
  - `a=group:DUP` for ST 2022-7 redundant legs (RFC 7104);
  - **`a=ts-refclk:ptp=IEEE1588-2008:<gmid>[:<domain>]`** and `a=mediaclk:direct=<offset>`
    ([RFC 7273 §4.8, §5][rfc7273]). The ABNF accepts both `domain-nmbr=` and a bare
    domain-name form, so the parser accepts both.

The `ts-refclk` grandmaster lets central cross-check each flow against the observed PTP Domain.
**A flow whose declared grandmaster differs from the grandmaster actually observed is a strong
predictor of receivers muting.** This needs no query.

**Read-only:** a pure listener. **Privacy and isolation:** SDP bodies contain internal
addressing, so the collector reduces each one to a **Media Flow** DTO with an opaque,
segment-salted flow key and no addresses (#375, item 6).

### 2.2 RAVENNA DNS-SD and RTSP

From the RAVENNA Operating Principles ([§3.4–3.5][ravenna-op]):

- Nodes register `<vendor node id>._rtsp._tcp`, `<vendor node id>._http._tcp`, and the
  `_ravenna._sub._rtsp._tcp` and `_ravenna._sub._http._tcp` subtypes.
- Advertised sessions carry the `ravenna_session` sub-service.
- "The RTSP DESCRIBE method is used by the client to retrieve the session description in SDP
  format".

`DESCRIBE` is read-only. `SETUP` and `PLAY` would create a session and **start a unicast media
stream toward the collector**, so the RTSP guard admits only `OPTIONS` and `DESCRIBE`.

### 2.3 AMWA NMOS IS-04, IS-05, IS-12, and BCP-008

All of these are on [specs.amwa.tv](https://specs.amwa.tv) and their GitHub repositories are
Apache-2.0 ([is-04][is04-repo], [is-05][is05-repo], [is-12][is12-repo],
[bcp-008-01][bcp00801-repo]).

**IS-04 discovery** ([IS-04 v1.3.3, *Discovery*][is04-disc]):

- Service types are `_nmos-register._tcp`, `_nmos-query._tcp`, `_nmos-node._tcp`, and legacy
  `_nmos-registration._tcp`.
- Unicast DNS-SD is tried first when DNS is configured, with fallback to mDNS. "Peer-to-peer
  mode only supports multicast operation."

**IS-04 Query API** ([IS-04 v1.3.3, *Behaviour – Querying*][is04-query]):

- `GET` on nodes, devices, sources, flows, senders, and receivers is read-only. A flow's
  `format` (`urn:x-nmos:format:audio`, `…:video`, `…:data`, `…:mux`) gives a second, independent
  video/audio classification for the join guard.
- Change notification is a `POST /subscriptions` followed by a WebSocket on the returned
  `ws_href`. That POST creates registry-side state.
- With `persist: false`, "The Query API MAY remove any Subscriptions … that no longer have
  WebSocket connections", and it "MUST NOT acknowledge HTTP DELETE requests" for them. The
  state is ephemeral and tied to micboard's connection. That makes it a sound **named ADR-016
  exception**: exactly `POST …/query/{ver}/subscriptions` with `persist: false`.
- **The Registration API is never called.** Calling it would register micboard as a Node.
- The registry plays the same role as a Device Manager (ADR-015 clause 4): it serves devices'
  state on their behalf.

**IS-05:**

- `GET /single/senders/{id}/transportfile` returns the sender's SDP, and `GET …/active` returns
  the active transport parameters. Both are read-only.
- `PATCH …/staged` makes connections and is denied.

**BCP-008-01 Receiver Status Monitoring** (v1.0.0) ([Overview][bcp00801]) defines, for each
receiver:

- `overallStatus`, `linkStatus`, `connectionStatus`, `externalSynchronizationStatus`, and
  `streamStatus`, each with messages and transition counters;
- `GetLostPacketCounters` and `GetLatePacketCounters`.

`connectionStatus` is "Unhealthy when the receiver is Active and is either not receiving any
packets or receiving packets but has unrecoverable errors". This is the **receiver's own loss
measurement**, so micboard needs no IGMP join for it.

**IS-12 transport** ([*Protocol messaging*][is12-msg]):

- WebSocket message types are `Command`, `CommandResponse`, `Notification`, `Subscription`,
  `SubscriptionResponse`, and `Error`.
- The guard admits a `Command` only for the `Get` method and the two counter getters, and admits
  `Subscription` messages.
- Writable properties (`statusReportingDelay`, `autoResetCountersAndMessages`) and
  `ResetCountersAndMessages` are denied, because they would change other controllers' view.

**nmos-cpp** (Sony, **Apache-2.0**) ([repo][nmoscpp]) is a Registry and Node in C++ for IS-04
and IS-05. Use its registry container in CI as the test target. The AMWA `nmos-testing` tool is
also Apache-2.0 ([repo][nmostesting]). Apache-2.0 is compatible with (A)GPLv3, so the JSON
schemas can be vendored with their NOTICE if needed.

**Reachability:** a registry is often on a control network, not the media VLAN. The NMOS
plugin runs in whichever segment collector has a route to it, or centrally if central can reach
it under network policy (the "add by IP" path in #355).

## 3. Dante

### 3.1 Passive: mDNS and heartbeats

**Ports and groups**, from Audinate's network-administrator note ([DDM network admin §3][ddm-netadmin]):

| Traffic | Address and port |
|---|---|
| mDNS and DNS-SD discovery | `224.0.0.251:5353/UDP` |
| PTP | `224.0.1.129`–`.132`, ports 319/320 |
| Dante multicast audio | `239.255/16:4321`. Unicast audio uses `14336`–`14600/UDP`. |
| "Dante-specific monitoring traffic" | `224.0.0.230`–`224.0.0.233:8700–8708/UDP` |
| Audio setup | `4455/UDP` |
| DDM | devices to DDM on `8000/UDP`, controllers on `8001/TCP` and `8443/TCP` |

**mDNS service types**, as browsed by netaudio ([`_protocols.py`][nac-protocols]):

- `_netaudio-arc._udp`, `_netaudio-chan._udp`, `_netaudio-cmc._udp`, `_netaudio-dbc._udp`;
- `_dantevideo._udp`, for Dante AV.

DDM is found through unicast DNS-SD as `_dante-ddm-c._tcp` and `_dante-ddm-d._udp`
([DDM network admin §2.4][ddm-netadmin]).

From announcements alone, a collector learns:

- that a device exists;
- its advertised name, host, and port;
- the TXT keys netaudio parses (`id`, and `server_vers` on `cmc`) ([`browser.py`][nac-browser]);
- each channel's existence, from `_netaudio-chan`;
- that a device left, from an mDNS goodbye (a record with TTL 0, [RFC 6762 §10.1][rfc6762]).

**Heartbeats:** netaudio listens on `224.0.0.233`, port 8708 ([`_abi.py`][nac-abi],
[`heartbeat.py`][nac-heartbeat]), and parses from heartbeats:

- the device's extended unique identifier;
- **clock frequency offset** records;
- interface traffic;
- **receiver connection health** (latency and late-packet records);
- signal presence.

It marks a device offline after 15 s without a heartbeat (`OFFLINE_THRESHOLD_SECONDS = 15.0`).

These formats are **reverse engineered, not published by Audinate**. A Dante plugin that uses
them stays an *unverified vendor* until captured fixtures exist (ADR-016 clause 10).

**Join cost:** `224.0.0.x` is link-local. RFC 4541 says snooping switches "must" forward
non-IGMP packets in `224.0.0.X` "on all ports" ([RFC 4541 §2.1.2][rfc4541]). Heartbeats
therefore already reach the collector's port, and listening adds no traffic to the link.

### 3.2 Queries: control ports versus the Dante Managed API

- **Control ports** (UDP 4440 and 8800, which netaudio uses for device info, routing, and
  settings) carry a single undocumented opcode space mixing reads and writes. **Skip:** an
  allowlist built from reverse engineering is too risky for default-deny, until captures pin
  exact read opcodes.
- **The Dante Managed API** ([User Guide v1.8][dante-mapi]; [product page][dante-mapi-page]):
  - **Availability:** released in DDM 1.5. It is GraphQL at `<ddm>/graphql` or Dante Director's
    `api.director.dante.cloud/graphql`. "Access to the API is included free-of-charge for all
    Dante Domain Manager, Dante Director and Dante Connect customers." DDM itself needs a paid
    licence.
  - **Keys:** "API keys do not expire but they can be revoked." "The API key will share the
    user's privileges," so Audinate advises creating a dedicated user to restrict a key.
    micboard documents a low-privilege user.
  - **`Query`:** `domains`, `domain(id)`, `deviceEntitlements`, and `unenrolledDevices`.
    - `Device` exposes `connection { state, lastChanged }`, with `ConnectionState`
      `DISCONNECTED`, `ESTABLISHED`, or `READY`.
    - `ClockingState` exposes `locked` (`LOCKED`, `NOT_LOCKED`, `UNKNOWN`), `grandLeader`,
      `followerWithoutLeader`, `muteStatus` (`MUTED_EXTERNAL_CLOCK`, `MUTED_INTERNAL_CLOCK`, …),
      and `frequencyOffset`.
    - `status { clocking, connectivity, latency, subscriptions, summary }` is `OK`, `WARNING`,
      `ERROR`, or `UNKNOWN`.
    - `rxChannels[].status` has a detailed `RxChannelStatus` enum.
  - **`Mutation`:** enrol and unenrol devices; set subscriptions; manage domains; set clocking
    (preferred leader, unicast, sync to external); rename devices. All are denied.
  - **No GraphQL `Subscription` type** appears in the schema, so the plugin polls.
  - **Limitations:** legacy-mode devices (generally firmware before 4.0) and Shared Audio Group
    virtual devices are not shown. "Only native Dante flows are supported", so AES67 and ST 2110
    subscriptions come from SAP and NMOS instead.
  - **Read-only guard:** parse each document with graphql-core (MIT) ([repo][graphql-core]) and
    admit it only if every operation is `query` and every root field is on an allowlist.

### 3.3 Open-source Dante tools

| Project | License | Protocol use | Verdict |
|---|---|---|---|
| netaudio / network-audio-controller ([repo][nac]) | **Unlicense** (`pyproject.toml`: `license = "Unlicense"`) | Discovery, heartbeats, and metering (passive), plus routing, settings, presets, and DDM control (writes) | Reference only. Its constants and parsers document the formats. Don't depend on it, because it is a controller. |
| Inferno ([repo][inferno]) | GPL-3.0-or-later **or** AGPL-3.0-or-later (README, "License") | An unofficial Dante **endpoint** implementation (sends and receives audio) | Skip at runtime. It could emit heartbeats and mDNS for hand-written fixtures. |

## 4. Stream health without bandwidth harm

### 4.1 RTP loss metrics

RFC 3550 Appendix A.1 and A.3 define the per-source counters: the extended highest sequence
number, expected = extended max − base + 1, cumulative lost = expected − received, and the
interval fraction lost. A.8 defines interarrival jitter ([RFC 3550][rfc3550]). A probe also
records reorders, duplicates, SSRC changes, and the longest gap in packet times. For an
ST 2022-7 flow, each `DUP` leg is measured separately.

### 4.2 Bandwidth: what one join costs

The numbers below are computed with 40 B of IP, UDP, and RTP headers and 42 B of Ethernet
overhead (preamble, VLAN tag, FCS, inter-frame gap) per packet:

| Flow | Payload per packet | Packets per second | On the wire |
|---|---|---|---|
| AES67, 2 ch L24, 48 kHz, 1 ms | 288 B | 1,000 | ≈ 3.0 Mbit/s |
| ST 2110-30, 8 ch L24, 48 kHz, 1 ms | 1,152 B | 1,000 | ≈ 9.9 Mbit/s |
| ST 2110-30, 64 ch L24, 48 kHz, 125 µs | 1,152 B | 8,000 | ≈ 79 Mbit/s |
| ST 2110-20, 1080p59.94 4:2:2 10-bit (active video alone) | n/a | n/a | ≈ 2.5 Gbit/s |
| ST 2110-20, 2160p59.94 4:2:2 10-bit | n/a | n/a | ≈ 10 Gbit/s |

One wrong join can saturate the listener's port. On an 802.1Q trunk (#375 item 1), it also
saturates the link shared by **every** segment's collector on that host.

### 4.3 IGMP implications inside a segment

- A socket join makes the host send an IGMP Membership Report ([RFC 3376][rfc3376]). A snooping
  switch then forwards that group to the listener's port ([RFC 4541 §2.1.2][rfc4541]). **A join
  changes switch forwarding state**, so it is not a pure read. It is a budgeted action.
- **Groups that cost nothing** because they are flooded anyway: `224.0.0.x` (mDNS, Dante
  monitoring and heartbeats).
- **Groups that cost a little:** PTP `224.0.1.129` and SAP `239.255.255.255`.
- **Without snooping or a querier,** every multicast floods to every port, video included. The
  collector reports this as a segment finding ("unpruned multicast", from interface receive
  counters). It neither causes nor worsens the condition.
- **Source-specific joins:** use IGMPv3 joins (RFC 4607) when SDP has `a=source-filter`, so a
  probe never pulls a second sender on the same group.
- **The collector never acts as an IGMP querier** and runs no multicast routing (#375 item 4).

### 4.4 The join guard: video essence is never joined

Three independent layers protect the budget:

1. **Classification.** A group is joinable only if its flow is known from SDP (via SAP, RTSP, or
   IS-05) with `m=audio` and an `rtpmap` encoding in {`L16`, `L24`, `AM824`}. Where IS-04 knows
   the flow, its `format` must also be `urn:x-nmos:format:audio`. Unknown, `video`, `raw`,
   `jxsv`, `smpte291`, `_dantevideo`, and Dante native flows are denied.
2. **Bitrate cap.** The collector computes the bitrate from `rtpmap` and `ptime`. A flow is
   denied if the bitrate is not computable, above a per-flow cap (default 100 Mbit/s), or would
   take the host over its per-host budget (default 200 Mbit/s across all segments). Probes are
   time-boxed (default 10 s windows, round-robin), so loss sampling is periodic, not continuous.
3. **Watchdog.** If the segment interface's measured receive rate exceeds the budget, the
   collector leaves every probe group at once and raises a critical "probe budget exceeded"
   fact.

A second, independent nftables layer (#375 item 8) counts segment-side multicast by group
range. The startup self-check refuses to start if the probe is enabled with no budget.

Python throughput at 1,000–8,000 packets/s per flow is fine for a few concurrent probes, but
dozens are not (*unverified*, measure). That is another reason to prefer receiver-reported
health (BCP-008, Dante heartbeats, the Dante Managed API) and to treat the probe as a fallback.

## 5. License summary (AGPL-3.0-or-later)

| Component | License | Compatible to combine? | How micboard uses it |
|---|---|---|---|
| linuxptp | GPL-2.0-or-later | Yes, via "or later" | External process only |
| Scapy | GPL-2.0-only ([`packet.py` SPDX][scapy]) | **No** | Not used |
| Wireshark | GPL-2.0 (GitHub detection) | Not needed | Developer tool |
| nmos-cpp, AMWA specs, nmos-testing | Apache-2.0 | Yes | CI registry container; schemas if vendored with NOTICE |
| netaudio | Unlicense | Yes | Reference |
| Inferno | GPL-3.0+ or AGPL-3.0+ | Yes | Not used at runtime |
| EBU LIST (pi-list) | GPL-3.0 (GitHub detection) ([repo][pilist]) | Not needed | Not used |
| python-zeroconf | LGPL-2.1-or-later ([pyproject][zeroconf]) | Yes | mDNS browsing if needed |
| dpkt | BSD-style ([LICENSE][dpkt]) | Yes | Not needed: in-house `struct` parsers |
| graphql-core | MIT | Yes | Query-only guard for the Dante Managed API |
| Dante Managed API | Proprietary service, free with DDM, Director, or Connect | No code is combined | HTTP client only |

## 6. Recommended design

### 6.1 The media segment collector

A **Media Segment Collector** is the existing segment collector (#375) with the media
components enabled. It runs in the segment's namespace and owns:

| Component | Listens to | Sends | Emits |
|---|---|---|---|
| PTP observer | `224.0.1.129:319/320` (v1 and v2) | nothing (IGMP join only) | `PtpDomainObservation` |
| Probe clock (opt-in) | ptp4l `uds_ro_address`, `slave_event_monitor` | Delay_Req via ptp4l (named exception) | `ProbeClockSample` |
| SAP listener | `239.255.255.255:9875` | nothing | `MediaFlow` facts |
| DNS-SD browser | `224.0.0.251:5353` | mDNS queries (read-only) | `MediaEndpoint` facts (RAVENNA, NMOS, Dante) |
| RTSP describer | RAVENNA nodes found by DNS-SD | `OPTIONS`/`DESCRIBE` only | `MediaFlow` facts |
| Dante heartbeat listener | `224.0.0.230`–`.233:8700–8708` | nothing | `MediaEndpoint` online, `ReceiverHealth` |
| Flow probe (opt-in) | budgeted audio groups | IGMP joins and leaves | `FlowHealthSample` |

Device Manager connections, which follow ADR-015 topology and run wherever the manager is
reachable:

- the **NMOS registry** (IS-04 Query, IS-05 GET, and IS-12/BCP-008 GET to nodes);
- the **Dante Managed API** (GraphQL query-only).

**Mapping to ADR-015:**

- **Vendor plugins.** `nmos` (manager topology), `dante` (direct for heartbeats and mDNS;
  manager for DDM or Director), and `aes67` (direct, covering SAP and RAVENNA). They implement
  the existing *discovery*, *inventory*, *realtime stream*, and *health* protocols.
- **The PTP observer and flow probe are not vendor plugins.** Each is a segment-level component
  that every media plugin depends on. They use a new capability protocol, **`SegmentObserver`**,
  so orchestration can start them per segment and the self-check can enumerate their join
  allowlists.

### 6.2 New domain concepts (proposed glossary entries for `CONTEXT.md`)

**Media Endpoint**:
A networked audio or video device that sends or receives media flows, identified by its
protocol's stable identity (Dante device ID, NMOS device ID, RAVENNA vendor node ID).
_Avoid_: Node (an NMOS-specific term), device (unqualified)

**Media Flow**:
One announced stream of media from a sender, described by SDP or an NMOS flow, with a media kind
(audio, video, data) and an optional reference clock.
_Avoid_: Stream (ambiguous with realtime transport), channel (reserved for RF channels),
subscription (a Dante routing term)

**Flow Leg**:
One of the redundant network paths of an ST 2022-7 Media Flow.
_Avoid_: Path, network (as a synonym)

**PTP Domain**:
The set of PTP clocks on a segment sharing one domain number, with at most one grandmaster at a
time.
_Avoid_: Domain (unqualified; collides with Dante Domain and DNS domain), clock domain

**Grandmaster**:
The clock currently selected by the BMCA as the time source of a PTP Domain, identified by its
clock identity.
_Avoid_: Master clock, leader (Dante's UI term), GM (in user-facing text)

**Dante Domain**:
A group of Dante devices enrolled together in Dante Domain Manager or Dante Director (a "site"
in Director).
_Avoid_: Domain (unqualified)

**Media Segment Collector**:
A segment collector with media observation enabled; it observes PTP, announcements, and
heartbeats on one isolated segment and never forwards media.
_Avoid_: Media proxy, tap, sniffer

**Flow Probe**:
A time-boxed, budgeted IGMP join to an audio Media Flow to measure RTP loss; never used on
video.
_Avoid_: Monitor stream, subscribe (Dante routing term)

**Probe Clock**:
An opt-in, client-only PTP clock run by a collector that measures its own offset from the
Grandmaster without steering the host clock.
_Avoid_: Slave (deprecated in IEEE 1588-2019 usage), PTP monitor

**Expected Flow**:
A Media Flow an operator has marked as required, so its disappearance raises an alert rather
than an inventory change.
_Avoid_: Pinned flow, critical stream

### 6.3 DTOs

All DTOs are Pydantic v2 on `PydanticBaseDTO`, frozen, and pass the ADR-016 allowlist scrubber.
They carry no IP addresses, MACs, multicast groups, or raw SDP. Keys are opaque and salted per
segment.

```python
class PtpDomainObservation(PydanticBaseDTO):
    segment_id: str
    domain_number: int
    ptp_version: Literal[1, 2]
    profile_guess: Literal["aes67", "st2059_2", "dante_v1", "default", "unknown"]
    grandmaster_identity: str | None          # EUI-64; None when no Announce seen
    grandmaster_priority1: int | None
    grandmaster_priority2: int | None
    clock_class: int | None
    clock_accuracy: int | None
    offset_scaled_log_variance: int | None
    time_source: str | None
    steps_removed: int | None
    log_announce_interval: int | None
    log_sync_interval: int | None
    two_step: bool | None
    announcing_masters: int                    # >1 sustained = competing masters
    follower_count: int                        # distinct Delay_Req senders (E2E)
    sync_gap_max_ms: float | None
    observed_at: datetime

class ProbeClockSample(PydanticBaseDTO):
    segment_id: str
    domain_number: int
    grandmaster_identity: str
    timestamping: Literal["hardware", "software"]
    offset_ns_p50: int
    offset_ns_p99: int
    offset_ns_max_abs: int
    path_delay_ns_p50: int
    window_s: int
    observed_at: datetime

class MediaEndpoint(PydanticBaseDTO):
    endpoint_key: str                          # opaque, from protocol identity
    protocol: Literal["dante", "ravenna", "aes67", "nmos"]
    name: str
    manufacturer: str | None
    model: str | None
    online: bool
    sources: frozenset[Literal["mdns", "heartbeat", "sap", "rtsp", "nmos", "dante_api"]]
    ptp_clock_identity: str | None
    clock_locked: bool | None                  # device-reported (Dante API, BCP-008)
    frequency_offset: int | None               # device-reported, unit per source
    last_seen_at: datetime

class MediaFlow(PydanticBaseDTO):
    flow_key: str                              # opaque: SDP origin or NMOS sender id
    sender_endpoint_key: str | None
    media_kind: Literal["audio", "video", "data", "unknown"]
    encoding: str | None                       # L24, L16, AM824, raw, jxsv, smpte291
    sample_rate: int | None
    channels: int | None
    packet_time_us: int | None
    legs: int                                  # 2 for ST 2022-7 DUP
    ref_clock_grandmaster: str | None          # from a=ts-refclk
    ref_clock_domain: int | None
    est_bitrate_bps: int | None
    probe_eligible: bool                       # result of the join guard
    discovered_via: Literal["sap", "rtsp", "nmos", "dante_api"]
    last_announced_at: datetime | None
    withdrawn: bool                            # SAP deletion or NMOS removal

class FlowHealthSample(PydanticBaseDTO):
    flow_key: str
    leg: int
    window_start: datetime
    window_s: float
    expected: int
    received: int
    lost: int
    duplicated: int
    reordered: int
    max_gap_ms: float
    jitter_us: float | None
    ssrc_changed: bool

class ReceiverHealth(PydanticBaseDTO):
    endpoint_key: str
    receiver_key: str
    source: Literal["bcp008", "dante_heartbeat", "dante_api"]
    connection: Literal["healthy", "partially_healthy", "unhealthy", "inactive", "unknown"]
    synchronization: Literal["healthy", "partially_healthy", "unhealthy", "not_used", "unknown"]
    lost_packets: int | None
    late_packets: int | None
    observed_at: datetime
```

### 6.4 How alerts work

Alerts follow the #366 model: central evaluates rules over reported facts, with `for` durations,
hysteresis, grouping, and inhibition. All thresholds below are configurable defaults to be tuned
on hardware.

| Alert | Fires when | Severity | Clears | Inhibits or is inhibited by |
|---|---|---|---|---|
| **Grandmaster changed** | `grandmaster_identity` differs from the previous value for the same segment and domain | info (event) | n/a | |
| **Grandmaster unstable** | more than 2 changes in 10 min | warning | 30 min stable | |
| **No grandmaster** | no Announce for `announceReceiptTimeout` × the observed announce interval (floor 3 s) | critical | Announce seen for 10 s | **inhibits** every flow, Dante clock, and receiver-sync alert on that segment and domain |
| **Competing masters** | `announcing_masters > 1` for 10 s | critical | single master for 30 s | |
| **Grandmaster degraded** | `clock_class` or `time_source` moves away from the baseline recorded when the grandmaster became current (for example, it lost GPS) | warning | back to baseline | |
| **Flow clock mismatch** | an Expected Flow's `ref_clock_grandmaster` ≠ the observed grandmaster of `ref_clock_domain` | warning | match | inhibited by No grandmaster |
| **PTP offset** | device-reported: `clock_locked == false`, Dante `muteStatus = MUTED_*`, or BCP-008 `synchronization = unhealthy` for 5 s. Probe: `offset_ns_p99` above the threshold for 3 windows. | warning; critical when audio is muted | healthy for 30 s | inhibited by No grandmaster |
| **SAP flow disappeared** | an Expected Flow with no announcement for `max(3 × learned interval, 30 s)` | warning | announcement seen | inhibited by Collector offline |
| **SAP flow withdrawn** | a SAP deletion packet, or past the RFC 2974 cache timeout | info for unexpected flows; warning for Expected Flows | re-announced | |
| **RTP loss** | `lost / expected` above 0.1 % in a probe window, or `max_gap_ms` above 4 × the packet time. Per leg for ST 2022-7. Prefer `ReceiverHealth.connection = unhealthy` when available. | warning on one leg; critical on all legs or non-redundant | 3 clean windows | inhibited by No grandmaster, Collector offline |
| **Dante device offline** | an mDNS goodbye (immediate), or no heartbeat for `max(15 s, 5 × learned interval)`, or Dante API `connection.state = DISCONNECTED` | warning; critical if the endpoint feeds an Expected Flow | heartbeat seen | inhibited by Collector offline, "isolation broken" |
| **Probe budget exceeded** | the watchdog tripped | critical | operator acknowledges | suspends all flow probes on that host |

Every alert carries its evidence, per #366 item 9: the observed and previous grandmaster, the
announce timestamps, the window counters, and the source of the reading.

### 6.5 Where it belongs

**Inside micboard, as a sibling product area, not inside RF monitoring and not a separate
repository.**

- It reuses every hard part already decided:
  - the Edge Listener and per-segment namespaces (#375);
  - the plugin capability protocols and Device Manager topology (ADR-015);
  - the read-only guard, backoff, and scrubber (ADR-016);
  - alerting (#366), and tenancy.
  A separate product would duplicate all of it for one maintainer.
- Its vocabulary is different. Media Endpoint, Media Flow, PTP Domain, and Grandmaster share no
  terms with Wireless Chassis, Wireless Unit, or RF channel. It gets its own domain packages
  (`micboard/services/media/`, `micboard/models/media/`, and so on), its own dashboard area,
  and a feature switch, so RF-only deployments see nothing new.
- **The bridge between the areas is valuable and small.** Many wireless chassis have Dante
  outputs, so a Media Endpoint can link to the Wireless Chassis it belongs to (matched by
  manufacturer serial or an operator mapping). An operator then sees that a receiver's audio
  output lost clock next to its RF state.

## 7. Phased plan (one PR per phase)

| Phase | PR | Scope |
|---|---|---|
| 0 | `docs(adr): ADR-017 media segment observation` | Passive-first rule, the join guard and budget, "never video", named ADR-016 exceptions (IS-04 non-persistent subscription, probe clock Delay_Req), the `SegmentObserver` protocol, and the glossary terms in `CONTEXT.md`. |
| 1 | `feat(media): domain models and DTOs` | Models for Media Endpoint, Media Flow, and PTP Domain state; the DTOs above; read-only admin; migrations through django-safemigrate. No collectors. |
| 2 | `feat(media): passive PTP observer` | v1 and v2 Announce/Sync parser, `PtpDomainObservation`, and the grandmaster changed, no grandmaster, competing masters, and grandmaster degraded rules. Captured fixtures. |
| 3 | `feat(media): SAP/SDP and RAVENNA flow inventory` | SAP listener, RTSP `OPTIONS`/`DESCRIBE` guard, SDP reduction to scrubbed `MediaFlow`, Expected Flows, and the flow clock mismatch, flow disappeared, and withdrawn rules. |
| 4 | `feat(integrations): Dante passive plugin` | mDNS service types and the heartbeat listener (unverified tier), Media Endpoint online state, `ReceiverHealth` from heartbeats, and the Dante device offline rule. |
| 5 | `feat(integrations): NMOS registry plugin` | IS-04 Query `GET` and non-persistent subscription, IS-05 `GET`, and Device Manager topology. CI against an nmos-cpp registry container. |
| 6 | `feat(media): budgeted audio flow probe` | Join guard (classification, bitrate cap, host budget), watchdog, RFC 3550 counters, ST 2022-7 legs, and the RTP loss and probe budget exceeded rules. |
| 7 | `feat(integrations): Dante Managed API and BCP-008 receiver status` | GraphQL query-only guard, IS-12 `Get`/`Subscription` guard, and device-reported clock lock and loss feeding the PTP offset and RTP loss rules. |
| 8 | `feat(media): opt-in probe clock` | ptp4l `clientOnly free_running` as an external process, `pmc` over `uds_ro_address`, and `ProbeClockSample`. The named exception is tested. |

Phases 2–4 deliver value without any query or join. Phase 6 is the first that pulls media onto
the trunk, and it lands only after the guard ADR (phase 0) is accepted.

## Sources

- [RFC 2974, Session Announcement Protocol][rfc2974]
- [RFC 8866, SDP (obsoletes RFC 4566)][rfc8866]
- [RFC 7273, RTP Clock Source Signalling][rfc7273]
- [RFC 3550, RTP][rfc3550]
- [RFC 3376, IGMPv3][rfc3376]
- [RFC 4541, IGMP and MLD snooping switches][rfc4541]
- [RFC 6762, Multicast DNS][rfc6762]
- [RFC 4570, SDP source filters](https://www.rfc-editor.org/rfc/rfc4570)
- [RFC 4607, source-specific multicast](https://www.rfc-editor.org/rfc/rfc4607)
- [RFC 7104, SDP duplication grouping](https://www.rfc-editor.org/rfc/rfc7104)
- [AMWA IS-04 v1.3.3, Discovery][is04-disc]
- [AMWA IS-04 v1.3.3, Behaviour: Querying][is04-query]
- [AMWA IS-04 repository (Apache-2.0)][is04-repo]
- [AMWA IS-05 repository (Apache-2.0)][is05-repo]
- [AMWA IS-12 repository (Apache-2.0)][is12-repo]
- [AMWA IS-12, Protocol messaging][is12-msg]
- [AMWA BCP-008-01 v1.0, Overview][bcp00801]
- [AMWA BCP-008-01 repository (Apache-2.0)][bcp00801-repo]
- [nmos-cpp (Apache-2.0)][nmoscpp]
- [AMWA nmos-testing (Apache-2.0)][nmostesting]
- [Audinate, Dante Domain Manager: Information for Network Administrators v1.11][ddm-netadmin]
- [Audinate, Dante Managed API User Guide v1.8 (2025)][dante-mapi]
- [Audinate, Dante Managed API product page][dante-mapi-page]
- [RAVENNA Operating Principles, Draft 1.0][ravenna-op]
- [Juniper, PTP media profiles (AES67 and ST 2059-2 tables)][juniper-ptp]
- [linuxptp msg.h][lptp-msg]
- [linuxptp pmc.c (license header)][lptp-pmc]
- [linuxptp monitor.c (SPDX GPL-2.0+)][lptp-monitor]
- [linuxptp tlv.h][lptp-tlv]
- [linuxptp ptp4l(8) man page][lptp-man]
- [netaudio / network-audio-controller (Unlicense)][nac]
- [netaudio _protocols.py][nac-protocols]
- [netaudio _abi.py][nac-abi]
- [netaudio browser.py][nac-browser]
- [netaudio heartbeat.py][nac-heartbeat]
- [Inferno (GPL-3.0+ or AGPL-3.0+)][inferno]
- [Scapy packet.py (SPDX GPL-2.0-only)][scapy]
- [Wireshark mirror][wireshark]
- [EBU LIST (pi-list)][pilist]
- [python-zeroconf pyproject.toml][zeroconf]
- [dpkt LICENSE][dpkt]
- [graphql-core (MIT)][graphql-core]

[rfc2974]: https://www.rfc-editor.org/rfc/rfc2974
[rfc8866]: https://www.rfc-editor.org/rfc/rfc8866
[rfc7273]: https://www.rfc-editor.org/rfc/rfc7273
[rfc3550]: https://www.rfc-editor.org/rfc/rfc3550
[rfc3376]: https://www.rfc-editor.org/rfc/rfc3376
[rfc4541]: https://www.rfc-editor.org/rfc/rfc4541
[rfc6762]: https://www.rfc-editor.org/rfc/rfc6762
[is04-disc]: https://specs.amwa.tv/is-04/v1.3.3/Discovery/
[is04-query]: https://specs.amwa.tv/is-04/v1.3.3/Behaviour%20-%20Querying/
[is04-repo]: https://github.com/AMWA-TV/is-04
[is05-repo]: https://github.com/AMWA-TV/is-05
[is12-repo]: https://github.com/AMWA-TV/is-12
[is12-msg]: https://github.com/AMWA-TV/is-12/blob/v1.0.x/docs/Protocol%20messaging.md
[bcp00801]: https://github.com/AMWA-TV/bcp-008-01/blob/v1.0.x/docs/Overview.md
[bcp00801-repo]: https://github.com/AMWA-TV/bcp-008-01
[nmoscpp]: https://github.com/sony/nmos-cpp
[nmostesting]: https://github.com/AMWA-TV/nmos-testing
[ddm-netadmin]: https://dev.audinate.com/GA/ddm/technical-notes/network-admin/pdf/latest
[dante-mapi]: https://dev.audinate.com/GA/managed-api/userguide/pdf/latest/
[dante-mapi-page]: https://www.getdante.com/products/network-management/dante-managed-api/
[ravenna-op]: https://ravenna-network.com/wp-content/uploads/2020/02/RAVENNA_Operating_Principles_-_Draft_1.0_final.pdf
[juniper-ptp]: https://www.juniper.net/documentation/us/en/software/junos/time-mgmt/topics/topic-map/configure-ptp-media-profiles.html
[lptp-msg]: https://github.com/richardcochran/linuxptp/blob/master/msg.h
[lptp-pmc]: https://github.com/richardcochran/linuxptp/blob/master/pmc.c
[lptp-monitor]: https://github.com/richardcochran/linuxptp/blob/master/monitor.c
[lptp-tlv]: https://github.com/richardcochran/linuxptp/blob/master/tlv.h
[lptp-man]: https://github.com/richardcochran/linuxptp/blob/master/ptp4l.8
[nac]: https://github.com/chris-ritsen/network-audio-controller
[nac-protocols]: https://github.com/chris-ritsen/network-audio-controller/blob/master/packages/netaudio/src/netaudio/core/_protocols.py
[nac-abi]: https://github.com/chris-ritsen/network-audio-controller/blob/master/packages/netaudio/src/netaudio/core/_abi.py
[nac-browser]: https://github.com/chris-ritsen/network-audio-controller/blob/master/packages/netaudio/src/netaudio/dante/browser.py
[nac-heartbeat]: https://github.com/chris-ritsen/network-audio-controller/blob/master/packages/netaudio/src/netaudio/dante/services/heartbeat.py
[inferno]: https://github.com/teodly/inferno
[scapy]: https://github.com/secdev/scapy/blob/master/scapy/packet.py
[wireshark]: https://github.com/wireshark/wireshark
[pilist]: https://github.com/ebu/pi-list
[zeroconf]: https://github.com/python-zeroconf/python-zeroconf/blob/master/pyproject.toml
[dpkt]: https://github.com/kbandla/dpkt/blob/master/LICENSE
[graphql-core]: https://github.com/graphql-python/graphql-core
