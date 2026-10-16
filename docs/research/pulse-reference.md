---
title: "Research: What micboard Can Learn from Pulse"
---
> **Learn-only reference. Pulse has no license.** Pulse
> ([qubered/a2-monitor](https://github.com/qubered/a2-monitor)) publishes no license, so all
> rights are reserved by its author. Nothing from it may be copied into micboard: no code,
> schemas, field names, assets, or text. This page summarizes its documented *ideas* in our own
> words, with links, so that micboard can design its own versions. Any adopted idea must be
> written fresh against micboard's own model and ADRs.

**Question** ([#363](https://github.com/justprosound/django-micboard/issues/363), part of
[#321](https://github.com/justprosound/django-micboard/issues/321)): what can micboard learn
from Pulse, an on-premises, browser-operated audio and wireless monitoring platform for A1s and
A2s with Shure and Sennheiser EW-DX integrations?

**Date:** 2026-10-16. Sources are Pulse's own `docs/` tree on its default branch, read on that
date. Pulse marks most architecture pages as *Proposed* or as a *Hypothesis; no supporting
evidence*, and its MVP ADRs (0027 onward) as *Accepted for the local MVP only*. These are
design intentions, not field-proven behaviour. Pulse's integration pages say themselves that its
Shure and EW-DX tables are unverified against hardware.

## How the two products differ

Pulse is a single-production tool: one appliance beside one audio interface, capturing Dante or
USB audio so that A2s can listen to and replay any channel in a browser, with receiver telemetry
alongside. It models the show itself: productions, performances, cues, characters, and swaps.
micboard monitors wireless gear and performers across many tenants, sites, and vendors, does not
capture audio, and treats production hardware as read-only. So Pulse's audio, listening, replay,
cue, and chat machinery is out of scope. Its identity, alerting, degraded-mode, and vendor-adapter
thinking carries over well.

## Summary table

Verdicts: **Adopt** means build our own version of the idea as described. **Adapt** means
take the idea but change it to fit micboard's decisions. **Skip** means not for micboard.
"Map" refers to the decisions on [#321](https://github.com/justprosound/django-micboard/issues/321).

| # | Pulse idea | micboard decision | Verdict |
|---|---|---|---|
| 1 | Person/role intent kept apart from physical components; each component link has its own interval | [#360](https://github.com/justprosound/django-micboard/issues/360): Assignment windows on Events | **Adapt** |
| 2 | Corrections append a new interval and close the old one; nothing is rewritten | #360, `django-simple-history`, `ActivityLog` | **Adopt** |
| 3 | No open interval means an explicit "none", never the last closed row | #360 (assignment *current* only in window) | **Adopt** |
| 4 | Exclusive assets: overlapping claims on one asset are an error, not a tie-break | #360 (not stated) | **Adopt** |
| 5 | Full bitemporal (valid time and recorded time) model and "as known then" replay | none | **Skip** |
| 6 | Character/role, understudy, swing, cover as assignment types | #360 (Performer, Event, Assignment) | **Skip for now** |
| 7 | Mic element, accessory, and kit tracked as separate assets | `Accessory` model | **Skip** |
| 8 | Physical-swap state machine (reserved → verified → complete) | none | **Skip** |
| 9 | A transmitter's last known model survives a dropout | Shure track [#345](https://github.com/justprosound/django-micboard/issues/345) (not stated) | **Adopt** |
| 10 | Display names are never identifiers | existing PKs | **Adopt** (already held) |
| 11 | One server-owned alert state; every client reads it | [#356](https://github.com/justprosound/django-micboard/issues/356) | **Adopt** (confirms) |
| 12 | Raise delay, clear delay, acknowledgement that never clears, escalation re-arms an acknowledged alert | #356 (`for` / `keep_firing_for`, Alertmanager semantics) | **Adopt** |
| 13 | Silence alerting armed only after a channel is first heard | #356, `alert_on_audio_low` | **Adopt** |
| 14 | Alerts explain themselves: observation, threshold, duration, source | `Alert.channel_data` | **Adopt** |
| 15 | Alert policy per show, edited by operators | #356, `UserAlertPreference` | **Adapt** |
| 16 | Channels outside the running session go idle: loss/mute/silence suppressed, battery and RF quality still alert | #360 Event windows, #356 inhibition | **Adapt** |
| 17 | Sessions are never started by the clock | #360 (windows switch assignments automatically) | **Adapt**, **contradiction C1** |
| 18 | Battery checked against the length of the next session | none | **Adopt** |
| 19 | Shared, attributed mic checks that go stale when their subject changes | none | **Adapt** (later) |
| 20 | Operator-filed fault reports: task, promoted to incident by urgency or corroborating telemetry; shared, attributed dismissal | #356 alert instances | **Adapt** |
| 21 | Advisory product; a failure matrix with automatic behaviour, operator capability, and target per row | ADR-016, edge listener [#354](https://github.com/justprosound/django-micboard/issues/354) | **Adopt** |
| 22 | Stale values kept with a timestamp, never shown as healthy or as a low reading | ADR-016 clause 4, ADR-014 clause 6 | **Adopt** |
| 23 | When the server is unreachable, clients keep identity and withdraw every verdict to unknown | none | **Adopt** |
| 24 | Hierarchical health; overall state is the worst active degradation, never an average | ADR-016 clause 8 | **Adopt** |
| 25 | Hardware-adjacent node separate from the management backend, versioned contracts | #354 (edge listener, semver `hello`) | **Adopt** (confirms) |
| 26 | Offline root CA, purpose-bound signing keys, signed leases, CRLs in show packages | #354 row 16 (mTLS and CA skipped) | **Skip**, **contradiction C3** |
| 27 | Purpose separation of credentials and refusal to issue on an uncertain clock | #354 rows 14–15 | **Adapt** |
| 28 | Local SQLite with WAL and full sync; startup refuses an unknown schema | #354 (SQLite outbox), #358 | **Adopt** |
| 29 | Hash-chained, tamper-evident audit | `ActivityLog`, `ConfigurationAuditLog` | **Skip** |
| 30 | Every signal has a unit, source, interval, and cardinality limit; no names or addresses as metric labels | none | **Adopt** |
| 31 | Support bundles redacted, with planted canary secrets in tests | ADR-016 clause 9 (allowlist scrubber) | **Adopt** |
| 32 | Browser has no route or credential to receivers | ADR-016 clause 7 | **Adopt** (confirms) |
| 33 | Shure TCP 2202 as primary, System API optional | #345 (`shure` and `shure-direct`) | **Adopt** (confirms) |
| 34 | Read `MODEL` and firmware first, then gate commands by a per-model capability profile | ADR-015 `Protocol`s and `PluginTraits` | **Adopt** |
| 35 | Stalled metering detected separately from a dead connection | ADR-016 clause 4 ("any traffic counts") | **Adapt**, **refinement C4** |
| 36 | Reconnect with jittered backoff, then publish one atomic snapshot | ADR-016 clause 1 | **Adopt** |
| 37 | Vendor meter scales kept as vendor values unless the vendor documents a conversion | ADR-014 clause 6 (RF level in dBm) | **Adapt**, **contradiction C2** |
| 38 | Firmware manifest per model: oldest and latest validated; untested known firmware is read-only; unknown major is unsupported | ADR-015 tier, ADR-016 clause 10 | **Adapt** |
| 39 | ANX4 channel count and mode discovered, never assumed; government ULX-D variants and SLX-D+ as distinct profiles | #345 (not listed) | **Adopt** |
| 40 | Meter-rate enable on Shure receivers generally | #345 / ADR-016 clause 12 (QLX-D never meters) | **Skip** (keep ours) |
| 41 | EW-DX: SSCv2 on firmware 4.0+, third-party access must be enabled; SSCv1 opt-in with a persistent warning | [#346](https://github.com/justprosound/django-micboard/issues/346) (`sennheiser-ssc1` as a normal plugin) | **Adapt** |
| 42 | Acceptance includes coexistence with vendor software, credential failure, connection limits, and startup storms | [#329](https://github.com/justprosound/django-micboard/issues/329), [#351](https://github.com/justprosound/django-micboard/issues/351), `quality.yaml` | **Adopt** |
| 43 | Rooms with per-room categories; a channel may be a member of several rooms, each with its own category | `Location`, `MonitoringGroup`, `DisplayWall` | **Adapt** |
| 44 | Each room runs its own session independently | #360 (Event has a location) | **Adopt** (confirms) |
| 45 | Alert counts stay global while the grid is filtered to one room | none | **Adopt** |
| 46 | Alert re-arm state keyed by channel, not by (channel, view) | #356 | **Adopt** |
| 47 | Room choice is a display preference, never a permission | `visible_to` (ADR-014 clause 5) | **Adopt** (confirms) |
| 48 | Transmitter form factor inferred from the reported model; operator's value always wins; source of the value shown | `WirelessUnit.device_type` (direction only) | **Adapt** |
| 49 | Simulated devices labelled as simulated everywhere | #351 simulator and demo mode | **Adopt** |
| 50 | Units stored in Hz, dBm, dBFS; explicit unknown instead of magic numbers | `UNKNOWN_BYTE_VALUE = 255`, `frequency` as text | **Adopt** |
| 51 | Alert rules offered only for capabilities the device actually reports | ADR-015 capabilities | **Adopt** |
| 52 | Audio capture, listen, replay, cues, chat, tasks, shift handoff, priority pages | out of scope | **Skip** |

## Time-bounded identity

### What Pulse does

Pulse's [temporal identity](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/temporal-identity-and-swap.md)
and [domain model](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/domain-model.md)
pages separate three things that micboard currently joins in one row:

- **who should be on a track**: a person cast in a role (character) for a performance, with an
  assignment type such as principal, understudy, swing, cover, or emergency;
- **what physical parts are on that track**: a mic element, a transmitter, a receiver path, and a
  captured audio input, each related to the track by its *own* time interval; and
- **what the signal path is actually doing**, recorded as an observed state (no path, partial,
  associated but unverified, and so on) without inventing a component boundary.

Every relationship carries a half-open interval. A swap closes the old component's interval at the
moment it was disconnected and opens the new one when it was installed, as separate events, so a
staggered pack change is never shown as simultaneous. If no interval is open, the answer is an
explicit "none" rather than the most recently closed row. Corrections append a new row that
supersedes the old one, and two rows claiming the same exclusive asset at once make the
projection invalid instead of being silently tie-broken. Pulse also stores *recorded* time (when
the system learned a fact) alongside *valid* time (when it was true), so replay can show what was
known during the show. A state machine guides physical interventions such as quick changes.
Reusable checks are tied to the exact tuple of performer, components, and path, with maximum ages
per check dimension, and any tuple change invalidates them.

The [glossary](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/domain-glossary.md)
adds one rule worth keeping: display names, receiver channel numbers, and input labels are never
identifiers.

### Comparison with micboard

micboard's [#360](https://github.com/justprosound/django-micboard/issues/360) resolution gives
an `Assignment` optional `starts_at`/`ends_at`, groups assignments under an **Event**, and makes
an assignment *current* only inside its window. Today `PerformerAssignment` links a `Performer`
straight to a `WirelessUnit`, which is the field device bound to a chassis and slot.

- **Adapt (1):** keep #360's single Assignment, but state its window as half-open
  `[starts_at, ends_at)`. Record the *observed* transmitter separately from the *intended*
  assignment: when a unit's reported serial or model changes, close the current
  `WirelessUnitSession` and open a new one, so history shows the swap and an alert is attributed
  to the pack that was actually present. This gives most of Pulse's component-interval benefit
  without a second assignment table.
- **Adopt (2, 3, 4):** a changed assignment closes the old row and creates a new one rather than
  editing a past window. A query for the current assignment returns nothing when no window is
  open. Overlapping current assignments on one wireless unit are rejected, ideally by a
  PostgreSQL exclusion constraint on the window range, which is a schema change for #358's
  approval queue.
- **Skip (5):** full bitemporality. `django-simple-history` and `ActivityLog` already answer
  "who changed what, when". micboard has no replay that needs an "as known then" view.
- **Skip for now (6, 7, 8):** roles or characters, understudy types, element and kit tracking,
  and the swap state machine all belong to theatre show operations. If a theatre vertical needs
  them later, an optional assignment *kind* is the smallest step.
- **Adopt (9):** when a Shure receiver reports that no transmitter is linked, keep the last known
  transmitter model and update only the link state. A dead battery is not evidence that a
  different pack is on the channel
  ([ADR 0036](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0036-transmitter-type-detection-and-photo-fallback-icon.md),
  item 4). This belongs in the `shure-direct` transformer from #345.

## Explainable alerts and fault reports

### What Pulse does

[ADR 0027](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0027-mvp-live-monitoring-and-alerts.md)
moved alert evaluation out of each browser after two tablets disagreed about what was wrong. The
node measures, the backend judges, and every client renders one published state. A finding must
persist for a per-kind raise delay before it becomes an alert and be absent for a clear delay
before it clears. In Pulse's words, acknowledgement "records who and when and never clears". A
severity escalation re-arms an acknowledged alert, and critical overlays never expire. A silence
alert arms only after the channel has been heard since the backend started, so unused inputs stay
quiet before the show. Thresholds are part of the show and edited by operators. Channels get
stable IDs so alerts survive renames.

[ADR 0028](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0028-mvp-shared-checks-and-fault-reports.md)
adds two shared, attributed workflows. **Mic checks** record who gave each verdict and go stale
when their subject (input patch, receiver channel, performer) changes. **Fault reports** are filed
by the A1 in a few presses: the report is a task until the A1 marks it urgent or telemetry shows
a measured fault on the same channel, and then it becomes an incident whose resolution waits for
the reporter to confirm the symptom is gone.
[ADR 0034](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0034-shared-fault-report-dismissal.md)
makes dismissal shared and attributed instead of per device. The domain model keeps observed
facts, derived warnings, and suspected causes apart in an incident.

### Comparison with micboard

[#356](https://github.com/justprosound/django-micboard/issues/356) already chose Prometheus
`for`/`keep_firing_for` semantics and Alertmanager-style routing, grouping, inhibition, and
silences, with alerts split into an instance and its notifications. Pulse independently arrives
at the same lifecycle, which is good confirmation.

- **Adopt (11, 12):** one alert instance per fingerprint, shared by every viewer. Acknowledgement
  is attributed and never resolves an alert. Escalation in severity clears the acknowledgement.
  This replaces the current per-user `Alert` row, which #356 already plans to split.
- **Adopt (13):** first-signal arming for silence and loss alerts, re-armed when an assignment
  window opens.
- **Adopt (14):** every alert instance stores a typed record of why it fired: the observed value
  and unit, the rule and threshold, how long it held, the source (plugin and target), and the
  freshness of the data. `Alert.channel_data` is an untyped start; make it a Pydantic DTO.
- **Adapt (15):** Pulse scopes thresholds per show. micboard should resolve them in layers:
  tenant defaults, then monitoring group, then Event override. Per-user preferences decide only
  notification routing, never whether an alert exists.
- **Adapt (20):** an operator-filed report becomes another *source* of alert instance in #356's
  model, with claim, resolve, and reopen actions attributed to users. A report on a channel with a
  matching telemetry alert is grouped with it, which is Pulse's promotion idea expressed as
  Alertmanager grouping. Skip Pulse's A1 and A2 role surfaces; micboard's crews are monitoring
  groups.
- **Adapt later (19):** shared mic checks fit an Event workflow (a pre-show check per assignment
  that goes stale when the assignment or the observed transmitter changes), but nothing on the
  map needs them yet.

## Sessions, run of show, and idle channels

### What Pulse does

[ADR 0029](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0029-mvp-sessions-and-run-of-show.md)
adds an agenda of sessions, each listing the channels it uses and an optional presenter per
channel. A channel the running session does not use is idle: it raises no transmitter-loss,
mute, or silence alerts, but battery, RF level, link quality, interference, and clipping still
alert, because a dying pack or a live mic that nobody expects is still worth knowing about.
Starting a session re-arms loss and silence alerting. The turnover view lists what each channel in
the next session waits on, including a battery whose reported runtime is shorter than the next
session's scheduled length. Pulse explicitly rejected starting sessions automatically at their
scheduled time, because agendas run late and re-arming on the clock would recreate unattended
faults. An operator presses start.

### Comparison with micboard

#360 makes Event windows switch assignments on and off automatically, including recurring Events.

- **Adapt (16):** model idle suppression as #356 inhibition: a channel with no current assignment
  inhibits loss, mute, and silence alerts but never battery, RF quality, or interference alerts.
- **Adopt (18):** a "won't last" alert when a unit's reported battery runtime is shorter than the
  time left in its current or next assignment window. A battery that cannot be measured is a
  warning at turnover, not a pass.

**Contradiction C1 (17).** Pulse refuses clock-driven sessions; #360 relies on them. micboard's
case is different: at country scale many rooms run unattended, and nobody is there to press
start. Keep #360's windows, and borrow Pulse's concern: let an operator start or end an Event
early or late, record actual times beside scheduled ones, and give window edges a grace period
(a `keep_firing_for`-style hold) so a session that overruns doesn't instantly silence loss alerts
for the performer still on stage.

## Degraded modes and observability

### What Pulse does

Pulse calls itself advisory: the conventional console path is the fallback whenever it is
unavailable. Its [failure and degraded-mode contract](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/failure-and-degraded-modes.md)
is a matrix with one row per failure (backend restart, database loss, disk full, adapter crash,
receiver loss, certificate expiry, power loss, failed update, and more), each stating the
automatic behaviour, what the operator can still do, and a target. Last values are kept but marked
stale with a timestamp, with no inferred healthy state. A crashed receiver adapter makes only that
vendor's telemetry stale. After recovery, mismatched state is never merged silently. When the
backend is unreachable, [ADR 0027](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0027-mvp-live-monitoring-and-alerts.md)
has the client keep last-known identity and withdraw every verdict and alert to unknown.

[Observability](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/observability.md)
makes health hierarchical: each subsystem reports healthy, degraded, unavailable, or unknown, with
cause, freshness, and a safe operator action, and the overall state is the most important active
degradation rather than an average. Every signal declares a unit, source, interval, cardinality
limit, freshness threshold, and retention class, and names, addresses, and vendor strings are not
metric labels. Support bundles are explicit, bounded, previewable, and redacted, and tests plant
canary secrets to prove the redaction works.

### Comparison with micboard

- **Adopt (21):** a failure matrix page for micboard (central down, edge partitioned, Huey stalled,
  Channels layer down, plugin crash, auth failure, device busy, database full), each row naming
  the automatic behaviour, operator capability, and a test in the suite. ADR-016 and #354 already
  define most of the behaviour; the matrix makes it reviewable and testable.
- **Adopt (22, 23):** the UI must show stale data as stale, distinct from a low reading, and when
  the WebSocket to central drops, the browser keeps names and layout but greys every status to
  unknown instead of showing frozen green tiles.
- **Adopt (24):** aggregate tenant and site health as worst-of over ADR-016's status categories.
- **Adopt (30):** if micboard exports metrics, label them only with bounded IDs (tenant, plugin,
  status), never device names, hostnames, or IPs. This also serves the public-repo privacy rule.
- **Adopt (31):** add a canary-secret test to ADR-016's allowlist scrubber: plant known secrets in
  fixtures and diagnostics and assert they never appear in output.

## Offline operation, PKI, and persistence

### What Pulse does

[ADR 0001](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0001-three-component-boundary.md)
separates a hardware-adjacent node from the management backend and the web apps, with versioned
contracts even when they share a machine, so the node keeps running through a backend outage.
[Deployment](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/deployment.md)
starts with a single appliance, allows a split node later, and does not promise multi-node. It
binds services to named interfaces, never bridges the audio, receiver, and client networks, and
gives the browser no route or credential to receivers.
[ADR 0013](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0013-offline-pki-and-key-lifecycle.md)
gives each installation an offline root CA, an online intermediate, and separate signing keys per
purpose, with key IDs, signed revocation bundles distributed with show packages, and a rule that
backward or uncertain wall-clock movement blocks enrolment and new leases. During an offline show,
only already-issued, time-bounded leases are honoured.
[ADR 0010](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0010-persistence-recovery-and-migrations.md)
uses SQLite in WAL mode with full sync, acknowledges a command only after commit, uses
expand/migrate/contract with declared schema-version ranges, refuses unsafe writers at startup,
and hash-chains durable events.

### Comparison with micboard

[#354](https://github.com/justprosound/django-micboard/issues/354) already chose an edge listener
that dials out over one WSS connection, caches the last good configuration revision, buffers
transitions in a SQLite outbox, and enrols with a single-use bootstrap token exchanged for a
hashed per-edge credential. It explicitly skipped mTLS and a CA.

- **Adopt (25, 32):** confirms #354 and ADR-016 clause 7.
- **Skip (26), contradiction C3:** Pulse's offline PKI is the approach #354 row 16 rejected as too
  much plumbing for one maintainer. Keep #354. Pulse's case for PKI rests on signed leases for
  offline browser control of an audio node, which micboard does not need because it never
  controls hardware.
- **Adapt (27):** keep two narrow ideas. An edge credential must be usable only for the edge
  channel, never as a user API token, and vice versa. And the edge `hello` should report the edge's
  clock, so central can flag a skewed edge and fall back to receive time for its timestamps.
- **Adopt (28):** the edge's SQLite outbox uses WAL with `synchronous=FULL`, and an edge refuses to
  start against a schema version it doesn't know, in line with #354's version tiers and #358's
  expand/contract rules.
- **Skip (29):** hash-chained audit. Nothing on the map calls for tamper evidence.

## Shure metering

### What Pulse does

Pulse's [Shure integration](https://github.com/qubered/a2-monitor/blob/main/docs/integrations/shure-wireless.md)
uses the TCP 2202 command strings as its primary transport and treats System API as an optional
later path, because the service and its device matrix don't cover every family. It reads the
model and firmware first, then picks a per-model capability profile and command table, so it only
sends commands the model is expected to support. It asks for a meter rate and keeps high-rate
samples local. The parser handles fragmented and coalesced frames, unknown properties, and
unsolicited reports. Metering that has stalled is detected separately from a dead connection.
Reconnects use jittered backoff and then publish one coherent snapshot. Vendor meter scales are
kept and labelled as vendor values unless Shure documents a conversion, and unsupported metrics
are unavailable rather than zero. QLX-D's RF level, available only inside a packed sample message,
is left unavailable. ANX4's channel count and operating mode are discovered, government ULX-D
models are explicit variants, and SLX-D+ is a profile distinct from SLX-D. Each model gets a
firmware manifest: oldest and latest physically validated, excluded releases, and required
probes. Known but untested firmware starts read-only and an unknown major version starts
unsupported. Acceptance includes coexistence with Wireless Workbench and rejected unauthorized
writes.

### Comparison with micboard

[#345](https://github.com/justprosound/django-micboard/issues/345) already splits Shure into
`shure` (System API as a Device Manager) and `shure-direct` (TCP 2202), with `METER_RATE` as the
only named write.

- **Adopt (33, 34, 36):** confirms #345 and ADR-015. Reconnects should publish one full normalized
  snapshot before deltas resume.
- **Adapt (35), refinement C4:** ADR-016 clause 4 counts any traffic as "seen". Keep that as the
  online definition, and add a separate meter-freshness flag per channel, so a receiver that
  answers `GET` but has stopped metering reads as online with stale meters.
- **Adapt (37), contradiction C2:** ADR-014 clause 6 and `WirelessUnit.rf_level` assume a
  normalized dBm value. Where a vendor documents no conversion, micboard must not relabel a vendor
  scale as dBm. Keep the dBm field null in that case and carry the raw vendor value in a separate,
  labelled field (or in diagnostics). This tightens ADR-014 rather than reversing it.
- **Adapt (38):** record per-family firmware ranges (oldest and newest captured, known-bad
  releases) in `quality.yaml` next to the tier, and treat an unknown major firmware as
  unverified even inside a verified plugin.
- **Adopt (39):** add ANX4 (discovered channel count and mode), ULX-D government variants, and
  SLX-D+ as distinct profiles to #345's family list.
- **Skip (40):** Pulse plans meter-rate enablement across families and does not mention the
  QLX-D lockup that #342 found. Keep ADR-016 clause 12: QLX-D never meters.

## Sennheiser EW-DX

### What Pulse does

Pulse's [EW-DX page](https://github.com/qubered/a2-monitor/blob/main/docs/integrations/sennheiser-ew-dx.md)
targets firmware 4.0 and later over the authenticated SSCv2 OpenAPI, noting that third-party
access is off by default on the receiver and must be enabled deliberately. Pre-4.0 SSCv1 is never
enabled automatically: an operator opts in per node, acknowledges a persistent warning, and keeps
the receiver network isolated. SSCv1 and SSCv2 are separate test matrices, and acceptance covers
credential failure, connection limits, startup storms, and coexistence with Sennheiser's own
software.

### Comparison with micboard

[#346](https://github.com/justprosound/django-micboard/issues/346) plans `sennheiser` (SSCv2)
first, then `sennheiser-ssc1`, then `sennheiser-mcp`, with path-explicit read-only allowlists.

- **Adapt (41):** don't gate SSCv1 behind an opt-in, because most of micboard's protocols
  (Shure TCP 2202, MCP, Lectrosonics, Audio-Technica) are unauthenticated too, and the read-only
  guard is always on. Instead, mark unauthenticated plugins in `PluginTraits` and show that on the
  per-plugin docs page and badge from [#359](https://github.com/justprosound/django-micboard/issues/359),
  and have the `sennheiser` setup section say that third-party access must be enabled on the
  receiver.
- **Adopt (42):** add credential-failure, session-limit, startup-storm (via #351's scale mode),
  and vendor-software coexistence items to the `quality.yaml` checklist.

## Rooms and channel membership

### What Pulse does

[ADR 0030](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0030-mvp-rooms-and-categories.md)
adds rooms, each with ordered categories (stage, lectern, and so on), and gives each room its own
running session so a breakout turnover never idles the main room. A device shows one room at a
time, grouped by category, while the header's alert count stays show-wide.
[ADR 0035](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0035-multi-room-channel-membership.md)
lets a channel belong to several rooms, with the category chosen per membership, for shared
spares and comms. Alert re-arm state stays keyed by channel, and in-use status combines across
memberships. Room choice is a per-device preference, not a permission.

### Comparison with micboard

micboard places hardware in exactly one `Location` (building and room), and ADR-014 clause 5
scopes visibility through it. `MonitoringGroup` and `DisplayWall`/`WallSection` already group
what a crew sees.

- **Adapt (43):** keep one owning location per device for tenancy and visibility. Express
  "visible in several rooms" as view membership: a channel may appear in several wall sections or
  monitoring groups, each with its own heading. Never let view membership widen `visible_to`.
- **Adopt (44, 45, 46, 47):** Events per location turn over independently (already true under
  #360). Alert counts in the header stay tenant-wide while the grid is filtered. Alert state is
  keyed by channel, not by the view showing it. Room or wall choice is a display preference only.

## Transmitter-type detection

### What Pulse does

[ADR 0036](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0036-transmitter-type-detection-and-photo-fallback-icon.md)
infers a transmitter's form factor (handheld or bodypack) from the model code the Shure receiver
reports, using a naming pattern Pulse observed across Shure families. The operator's own value
always wins. The inferred value is computed when state is published and never written back to
configuration, and a separate field says whether the value came from the operator or was
inferred. A card with no photo shows a form-factor pictograph.

### Comparison with micboard

`WirelessUnit.device_type` records direction (mic transmitter, IEM receiver, transceiver), not
form factor, and nothing in micboard infers either.

- **Adapt (48):** add a form factor with a source (`operator` or `inferred`). The plugin's
  normalized unit DTO carries the inferred value. The operator's value, when set, always wins and
  is never overwritten. Don't rely on a suffix pattern: Shure also ships plug-on, boundary, and
  gooseneck transmitters, so each plugin should hold an explicit model-to-form-factor table built
  from the vendor's published model list and confirmed by captures, with unknown models left
  null.

## Smaller items

- **Adopt (49):** simulated targets from #351 carry a flag that the API and UI show everywhere, so
  demo data never reads as real
  ([ADR 0027](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0027-mvp-live-monitoring-and-alerts.md),
  item 5).
- **Adopt (50):** normalized DTOs use explicit `None` for unknown, never sentinels such as
  `WirelessUnit.UNKNOWN_BYTE_VALUE = 255`, and store frequency as an integer in a stated unit
  rather than text ([domain model, units](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/domain-model.md)).
  This fits the DTO boundary work in [#325](https://github.com/justprosound/django-micboard/issues/325).
- **Adopt (51):** alert rules apply only to capabilities a device reports. A unit that can't report
  battery gets no battery rule, and the UI says "not reported" rather than showing a pass.
- **Skip (52):** audio capture, WebRTC listening, replay, cues and occurrences, chat, tasks,
  priority pages, and shift handoff
  ([overview](https://github.com/qubered/a2-monitor/blob/main/docs/architecture/overview.md)).
  micboard does not carry audio, and crew collaboration belongs in tools crews already use.

## Contradictions with micboard decisions

| ID | Pulse | micboard | Recommendation |
|---|---|---|---|
| C1 | Sessions start only when an operator presses start ([ADR 0029](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0029-mvp-sessions-and-run-of-show.md)) | Event windows switch assignments automatically ([#360](https://github.com/justprosound/django-micboard/issues/360)) | Keep #360 for unattended rooms. Add operator start and end overrides, actual times, and a grace hold at window edges. |
| C2 | Vendor scales stay vendor values unless a conversion is documented ([Shure page](https://github.com/qubered/a2-monitor/blob/main/docs/integrations/shure-wireless.md)) | RF level in dBm (ADR-014 clause 6, `rf_level`) | Tighten ADR-014: dBm only when documented, otherwise null plus a labelled raw value. |
| C3 | Offline root CA and purpose-bound keys ([ADR 0013](https://github.com/qubered/a2-monitor/blob/main/docs/decisions/0013-offline-pki-and-key-lifecycle.md)) | mTLS and a CA skipped ([#354](https://github.com/justprosound/django-micboard/issues/354) row 16) | Keep #354. |
| C4 | Stalled meters detected separately from a dead connection | Any traffic counts as seen (ADR-016 clause 4) | Refine, don't reverse: add per-channel meter freshness. |

## Follow-ups this suggests

None of these is decided here; each would go through the map.

1. An ADR-014 amendment for C2 (dBm only when documented).
2. Exclusion constraint on assignment windows and swap-aware `WirelessUnitSession` (items 1–4),
   for #358's approval queue.
3. Typed alert evidence, layered thresholds, idle inhibition, operator reports, and the
   battery-versus-window alert, folded into the #356 alerting ADR.
4. A micboard failure-matrix page with a test per row.
5. Additions to #345 (ANX4, government ULX-D, SLX-D+, last-known model) and to the `quality.yaml`
   checklist (firmware ranges, coexistence, credential failure, startup storm).
6. Form factor with source on the normalized unit DTO.
