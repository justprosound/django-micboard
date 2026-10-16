---
title: "Research: Plugin-Architecture Patterns from Open-Source Integration Hubs"
---
**Question** ([#343](https://github.com/justprosound/django-micboard/issues/343), part of
[#321](https://github.com/justprosound/django-micboard/issues/321)): which patterns that mature
open-source integration hubs use for polling, availability, secret redaction, quality tiers, and
capability declaration fit micboard's plugin contract (ADR-015)?

**Date:** 2026-10-15. All sources are public. Source links point at each project's default
branch as read on that date, so line content may drift.

## Summary

The decisions in ADR-015 already match the hubs on the big shape: capabilities expressed in
code, facts in a frozen declaration, one owner per update model. The hubs add four things that
ADR-015 doesn't yet say:

1. **A typed "unavailable" signal that carries `retry_after`, with exponential backoff and
   jitter owned by orchestration, not by the plugin.** Home Assistant puts this in one place
   (`UpdateFailed` and the config-entry setup retry). Zigbee2MQTT applies the same idea per
   device.
2. **Authentication failure is a separate state that stops polling.** Home Assistant stops
   rescheduling the coordinator after `ConfigEntryAuthFailed` and asks the user to
   re-authenticate. Bitfocus Companion reports a distinct `authentication_failure` status.
   This matters for micboard: retrying bad credentials against a Device Manager can lock the
   account.
3. **Availability is "last seen within a timeout", logged once per transition.** Zigbee2MQTT
   computes it from `lastSeen`, and Home Assistant's quality scale requires one log line when a
   device goes offline and one when it comes back.
4. **Quality tiers are a per-integration checklist that CI validates.** Home Assistant's
   `quality_scale.yaml` marks each rule `done`, `todo`, or `exempt` with a comment, and
   `hassfest` enforces it. micboard's two-value tier can be backed by the same kind of file.

For redaction, Home Assistant's `async_redact_data` is a **denylist** of keys. micboard should
keep the fail-closed **allowlist** decided in #328 and reuse it for runtime diagnostics too.
From Node-RED and Companion it should borrow the rule that secrets are stored apart from
ordinary config and never sent back to the client.

## Recommendations

| # | Pattern (source) | Verdict | Concrete change to micboard |
|---|---|---|---|
| 1 | `UpdateFailed(retry_after=…)` plus setup retry `min(5·2ⁿ, 600 s)` with jitter (Home Assistant) | **Adopt** | Add an unavailable exception carrying `retry_after` to the existing hierarchy (ADR-009). Orchestration, not plugins, computes the next attempt and keeps backoff state in the database so every Huey worker sees it. |
| 2 | Randomised offset per coordinator against a thundering herd (Home Assistant, Zigbee2MQTT `max_jitter`) | **Adopt** | Add a random offset to each target's next poll time so targets with the same `poll_interval` don't fire together. |
| 3 | Auth failure stops polling and starts reauth (Home Assistant `ConfigEntryAuthFailed`) | **Adopt** | A plugin raises an authentication error, the connection moves to `auth_failure`, and polling and subscribing stop until an operator saves new credentials. ADR-015 should say that orchestration never retries an auth failure. |
| 4 | Status vocabulary: `ok`, `connecting`, `disconnected`, `connection_failure`, `bad_config`, `authentication_failure`, `insufficient_permissions` (Companion `InstanceStatus`) | **Adapt** | Replace the single `error` value in `RealtimeConnection` and the Device Manager connection with this split, shared by both. This is a choices change, so it needs migration approval. |
| 5 | Availability = `now − last_seen < timeout`, with a longer timeout for passive devices (Zigbee2MQTT) | **Adopt** | Any successful poll or pushed message refreshes `last_seen`. Derive the availability timeout from `PluginTraits` (a multiple of `poll_interval`, or the session heartbeat), with an optional override field. |
| 6 | Log once when a device becomes unavailable and once when it recovers (Home Assistant `log-when-unavailable`) | **Adopt** | Log at `info` and publish an event on transitions only, in the chassis lifecycle service, which already sees every transition. Never log per failed poll. |
| 7 | Notify listeners only when data changed (Home Assistant `always_update=False`) | **Adopt** | Compare the new frozen normalized DTO with the previous one and skip persistence and broadcast when they're equal. |
| 8 | Debounced "refresh now" (Home Assistant `request_refresh_debouncer`, 10 s cooldown) | **Adapt** | Debounce any operator-triggered refresh per target, inside the read-only guard's rate limit. |
| 9 | `PARALLEL_UPDATES` caps concurrent requests per platform (Home Assistant) | **Adopt** | State in ADR-015 that `session_limit` is enforced by a per-target semaphore in the transport, with a default of 1. |
| 10 | `async_redact_data(data, TO_REDACT)` denylist diagnostics (Home Assistant) | **Adapt** | Keep the #328 allowlist scrubber and use it for a per-connection diagnostics download too. Replace the substring denylist in `micboard/serializers/v1/discovery.py` with it. |
| 11 | Secrets kept apart from config, and only `has_<name>` sent to the editor (Node-RED credentials, Companion `secrets`) | **Adopt** | Write-only credential fields on the Device Manager connection. The API and admin return only `has_password: true` and never echo the value. |
| 12 | `quality_scale.yaml` with `done`, `todo`, or `exempt` plus a comment, validated by `hassfest` (Home Assistant) | **Adapt** | Give each plugin a small rule checklist. `verified` means every rule is `done` or `exempt`, and the ADR-015 clause 6 test grows to check the checklist, not only fixture existence. Skip the four-tier ladder. |
| 13 | `exposes` with a `STATE`/`SET`/`GET` access bitmask per feature (Zigbee2MQTT definitions) | **Skip** | Typed normalized DTOs plus capability protocols already declare what a plugin can report. Per-field metadata would duplicate them. |
| 14 | `PluginConfig` `min_version`, `max_version`, `required_settings` (NetBox) | **Skip** | micboard's plugins ship in-tree, so there's no version skew to guard. |
| 15 | One child process per module (Companion) | **Skip** | The realtime process plus Huey is the isolation boundary micboard already chose. |
| 16 | Feedback `subscribe`/`unsubscribe`, so polling covers only what's on screen (Companion) | **Skip** | micboard monitors every registered device whether or not anyone is watching. |

## 1. Polling coordination and backoff

### Home Assistant `DataUpdateCoordinator`

**Problem:** many entities need data from one endpoint, and naive per-entity polling multiplies
requests, scatters error handling, and floods logs.

**How it works** ([source](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/update_coordinator.py),
[docs](https://developers.home-assistant.io/docs/integration_fetching_data/)):

- One coordinator per endpoint owns `update_interval` and an `_async_update_data()` the
  integration implements. Entities subscribe as listeners.
- Each coordinator picks a random fraction of a second at construction "to stagger the refreshes
  and avoid a thundering herd" (`self._microsecond = randint(...)`).
- The integration raises `UpdateFailed(retry_after=...)` when the device is unreachable. The
  coordinator records `last_update_success = False`, logs the failure once while it stays
  failed, and logs "Fetching %s data recovered" once on recovery. If `retry_after` is set, the
  next refresh waits that long instead of `update_interval`.
- `ConfigEntryAuthFailed` sets `auth_failed`, so the `finally` block skips
  `_schedule_refresh()`. Polling stops, and `async_start_reauth_if_available` opens a reauth
  flow.
- `always_update=False` notifies listeners only when the data changed (`previous_data !=
  self.data`) or the success state flipped.
- `async_request_refresh()` goes through a `Debouncer` with
  `REQUEST_REFRESH_DEFAULT_COOLDOWN = 10` seconds.

The first refresh during setup turns failures into `ConfigEntryNotReady`. The config entry then
retries setup with `wait_time = min(2**self._tries * 5, SETUP_RETRY_MAX_WAIT)`, where
`SETUP_RETRY_MAX_WAIT = 600`. A server-supplied `retry_after` acts only as a floor, capped at one
day, and the jitter is added on top
([source](https://github.com/home-assistant/core/blob/dev/homeassistant/config_entries.py)).

**Fit:** good, with one translation. A coordinator is an in-process asyncio object. micboard's
poll path runs as Huey tasks across worker processes. That's why micboard's existing
`CircuitBreaker` (`micboard/services/common/base/circuit_breaker.py`), which keeps state on the
instance, is only shared by callers in one process. Backoff state therefore belongs in the
database: failure count and next attempt time per Device Manager connection or per direct
target. ADR-015 already needs a migration for the manager connection, so the fields can ride
along. The realtime process is long-lived asyncio and can hold state in memory like Home
Assistant does, but it should write the same fields so the admin shows one picture.

**Recommendation:** adopt items 1, 2, 3, 7 and 8 from the table. Plugins raise. They never sleep
or retry on their own, which keeps the backoff policy in one place.

### Zigbee2MQTT availability pings

**Problem:** know whether a mains-powered device is still there without hammering a constrained
network.

**How it works** ([source](https://github.com/Koenkk/zigbee2mqtt/blob/master/lib/extension/availability.ts),
[settings schema](https://github.com/Koenkk/zigbee2mqtt/blob/master/lib/util/settings.schema.json)):

- Any message from a device resets its timer, so a ping happens only after a quiet period of
  `timeout` (default 10 minutes active, 1500 minutes passive) plus up to `max_jitter`
  (default 30000 ms).
- Pings go through a single queue, with a 2-second pause between devices.
- A failed ping multiplies the device's timeout by 1.5 (if it was available) or 2, giving
  "×1.5, ×3, ×6, ×12…". Past `pause_on_backoff_gt` the device isn't pinged again until it sends
  something on its own.

**Fit:** good for direct-topology devices, especially session devices in the realtime process.
The serial queue matches the decided one-request-per-second-per-device live limit. Pausing
probes after repeated failure suits devices that are switched off between events.

**Recommendation:** adopt the "traffic resets the timer" rule (item 5) and the cap on backoff
growth. The fixed 2-second inter-device pause is Zigbee-specific. Skip it, because the read-only
guard's rate limit already covers it.

### Bitfocus Companion TCP helper

Companion's `TCPHelper` reconnects on a fixed `reconnect_interval` (default 2000 ms) with no
backoff, and leaves polling entirely to each module
([source](https://github.com/bitfocus/companion-module-base/blob/main/packages/base/src/helpers/tcp.ts)).
That works for a show-control console on a private network, but it's too aggressive for
production gear with a session limit. **Skip** the reconnect policy, but keep its idea that the
transport emits status changes (`status_change`), which is item 4.

## 2. Device availability and online state

| Hub | Model | Source |
|---|---|---|
| Home Assistant | An entity's `available` is `coordinator.last_update_success`. The `entity-unavailable` (Silver) rule requires marking entities unavailable on failure, and `log-when-unavailable` (Silver) requires one `info` log at the transition each way. | [`CoordinatorEntity.available`](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/update_coordinator.py), [rule](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/log-when-unavailable/) |
| Zigbee2MQTT | `isAvailable = Date.now() - lastSeen < timeout`. Active (mains) and passive (battery) devices get different timeouts. | [source](https://github.com/Koenkk/zigbee2mqtt/blob/master/lib/extension/availability.ts) |
| Companion | One `InstanceStatus` per connection: `ok`, `connecting`, `disconnected`, `connection_failure`, `bad_config`, `unknown_error`, `unknown_warning`, `authentication_failure`, `insufficient_permissions`, set through `updateStatus(status, message)`. | [enums.ts](https://github.com/bitfocus/companion-module-base/blob/main/packages/base/src/module-api/enums.ts), [base.ts](https://github.com/bitfocus/companion-module-base/blob/main/packages/base/src/module-api/base.ts) |
| OpenRemote | Agent `ConnectionStatus`: `DISCONNECTED`, `CONNECTING`, `DISCONNECTING`, `CONNECTED`, `DISABLED`, `WAITING`, `ERROR`, `STOPPED`. | [ConnectionStatus.java](https://github.com/openremote/openremote/blob/master/model/src/main/java/org/openremote/model/asset/agent/ConnectionStatus.java) |
| Node-RED | `node.status({fill, shape, text})`. A red ring means "disconnected" and a green dot means "connected". | [docs](https://nodered.org/docs/creating-nodes/status) |

The hubs separate two things micboard currently blurs:

- **connection state:** the session to a Device Manager or a device (Companion, OpenRemote,
  Node-RED);
- **device availability:** whether a given device answered recently (Home Assistant entities,
  Zigbee2MQTT).

micboard has the first in `RealtimeConnection.CONNECTION_STATUS` (`connecting`, `connected`,
`disconnected`, `error`, `stopped`, close to OpenRemote) and in `ManufacturerAPIServer.Status`
(`active`, `inactive`, `error`, `unknown`). It has the second in `WirelessChassis.is_online` and
`last_seen`, driven by the status transitions in
`micboard/services/hardware/chassis_lifecycle_service.py`.

**Recommendation:**

- **Adapt** Companion's vocabulary (item 4). Split `error` into `connection_failure`,
  `authentication_failure`, `bad_config`, and `insufficient_permissions`, and use one choices set
  for both connection models. The split decides behaviour: orchestration retries
  `connection_failure` with backoff and never retries the other three without operator action.
- **Adopt** last-seen availability (item 5) and log-once transitions (item 6) for devices. When a
  Device Manager connection fails, mark it failed, but don't flip every device it manages
  offline on the first miss. Let their own availability timeout expire, so one dropped manager
  poll doesn't light up the whole board.

## 3. Secret redaction in diagnostics

### Home Assistant `async_redact_data`

**How it works** ([source](https://github.com/home-assistant/core/blob/dev/homeassistant/components/diagnostics/util.py),
[docs](https://developers.home-assistant.io/docs/core/integration_diagnostics/)): an integration
implements `async_get_config_entry_diagnostics` and optionally
`async_get_device_diagnostics`, and passes its output through
`async_redact_data(data, TO_REDACT)`. The helper walks mappings and lists and replaces the value
of any key in `TO_REDACT` with `"**REDACTED**"`. It skips `None` and empty strings, so the output
still shows that a field was blank. Diagnostics is a Gold-tier rule.

**Fit:** the diagnostics *feature* fits well. A per-connection download from the admin gives
users a safe artifact to attach to a public issue. The *denylist* doesn't fit micboard's public
repo: a key the integration author didn't think of, such as a device name, serial, or a new
vendor field, passes through. #328 already decided a fail-closed allowlist scrubber with
RFC 5737 IPs and RFC 7042 MACs for fixtures.

**Recommendation:** **adapt** (item 10). Expose diagnostics through the same allowlist scrubber
that the fixture capture uses, so there's one redaction path to maintain. Keep Home Assistant's
detail of leaving `None` and empty values visible. Replace the substring denylist
`redact_sensitive_keys` in `micboard/serializers/v1/discovery.py` with that scrubber.

### Node-RED credentials and Companion secrets

- **Node-RED:** a node declares `credentials` fields of type `text` or `password`. They're
  "stored separately to the main flow file" and aren't included when flows are exported.
  `password` values are never sent to the editor, which gets only a boolean `has_<name>`
  ([docs](https://nodered.org/docs/creating-nodes/credentials)).
- **Companion:** `secret-text` config fields go to a separate `secrets` object passed to
  `init()` and `configUpdated()`
  ([source](https://github.com/bitfocus/companion-module-base/blob/main/packages/base/src/module-api/base.ts),
  [docs](https://companion.free/for-developers/module-development/connection-basics/overview)).
  The base class warns that "the whole config object and the keys of the secrets object are
  reported to the webui".

**Recommendation:** **adopt** (item 11). Device Manager credentials are write-only in DRF
serializers and the admin form, and reads return `has_password` instead. Because redaction is
structural, diagnostics and logs never have a secret to leak.

## 4. Per-integration quality tiers

### Home Assistant integration quality scale

**How it works** ([docs](https://developers.home-assistant.io/docs/core/integration-quality-scale/),
[validator](https://github.com/home-assistant/core/blob/dev/script/hassfest/quality_scale.py)):

- Four cumulative tiers (Bronze, Silver, Gold, Platinum) plus special labels (No score,
  Internal, Legacy, Custom).
- Each rule belongs to one tier. Examples: `appropriate-polling` and `test-before-setup`
  (Bronze); `entity-unavailable`, `log-when-unavailable`, `parallel-updates` and
  `reauthentication-flow` (Silver); `diagnostics` and `docs-supported-devices` (Gold);
  `strict-typing` and `inject-websession` (Platinum).
- Each integration keeps a `quality_scale.yaml` marking every rule `done`, `todo`, or `exempt`
  with a required comment. `hassfest` fails CI when a claimed tier has a rule that isn't `done`
  or `exempt`, and some rules have code validators that check the claim.

### NetBox

NetBox Labs runs a certified-plugin program with a co-maintainer relationship
([announcement](https://netboxlabs.com/blog/netbox-labs-announces-certified-and-supported-netbox-plugins/)).
That's a governance process, not a code mechanism, so there's nothing to borrow.

### Companion

The module manifest has a boolean `isPrerelease`
([schema](https://github.com/bitfocus/companion-module-base/blob/main/packages/base/assets/manifest.schema.json)),
a one-bit tier like micboard's.

**Fit:** a four-tier ladder is too much for one maintainer and a handful of vendors. The
checklist-plus-validator mechanism is cheap, and it says *why* a plugin is unverified.

**Recommendation:** **adapt** (item 12). Keep `PluginTraits.tier` at `verified` or
`unverified`. Each plugin carries a short checklist of about six rules, each `done`, `todo`, or
`exempt` plus a comment:

- fixtures captured;
- read-only policy tested;
- `retry_after` and auth failure mapped;
- availability timeout set;
- diagnostics scrubbed;
- supported models documented.

The ADR-015 clause 6 test then checks that `verified` means no `todo` remains, and checks
`fixtures captured` against the fixture directory. The checklist also gives the user-facing tier
docs from #321's "Not yet specified" list their content.

## 5. Declaring device capabilities

- **Zigbee2MQTT and zigbee-herdsman-converters:** each device definition lists `exposes`, and
  every feature carries an access bitmask `STATE = 0b001`, `SET = 0b010`, `GET = 0b100`
  ([exposes.ts](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/lib/exposes.ts),
  [types.ts](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/lib/types.ts)).
  The converter library also asserts that a diagnostic expose must not be settable.
- **NetBox:** `PluginConfig` declares `min_version`, `max_version`, `required_settings` and
  `default_settings`, and `validate()` raises `ImproperlyConfigured`
  ([source](https://github.com/netbox-community/netbox/blob/main/netbox/netbox/plugins/__init__.py)).
- **Companion:** the manifest declares `manufacturer`, `products`, `keywords`, and
  `bonjourQueries` for discovery.
- **Home Assistant:** `PARALLEL_UPDATES` in a platform module caps simultaneous requests to a
  device; `1` serialises and `0` removes the limit
  ([rule](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/parallel-updates/)).

**Fit:**

- micboard declares *what a plugin can do* with `typing.Protocol`s and *what it reports* with
  typed normalized DTOs, which is stronger than per-field metadata because code must exist to
  satisfy it. Zigbee2MQTT's `exposes` solves a different problem: thousands of generic device
  models rendered by one generic UI. **Skip** (item 13).
- NetBox's version bounds guard third-party plugins installed against an unknown host version.
  micboard's plugins live in `micboard/integrations/`. **Skip** (item 14).
- `PARALLEL_UPDATES` is the same fact as `PluginTraits.session_limit`. **Adopt** its
  enforcement (item 9): the limit is a semaphore in the transport, not advice.
- Companion's `products` list is a cheap source for the "supported models" documentation rule
  in section 4. Put the same list in the plugin's checklist file rather than a new trait.

## Proposed changes to ADR-015

1. **Clause 3, `PluginTraits`:** add an optional `availability_timeout`, defaulting to a
   multiple of `poll_interval` or the session heartbeat. State that `session_limit` is enforced
   by a per-target semaphore in the transport.
2. **New clause, failure signalling:** plugins raise one of two typed exceptions from the
   existing hierarchy: unavailable, with an optional `retry_after`, or authentication failed.
   Plugins never retry or sleep. Orchestration owns backoff, using `min(base·2ⁿ, cap)` with
   jitter and `retry_after` as a floor. Backoff state lives in the database so every Huey worker
   and the realtime process share it. Authentication failure stops polling and subscribing until
   an operator acts.
3. **New clause, state vocabulary:** one connection-status choices set: `ok`, `connecting`,
   `disconnected`, `connection_failure`, `authentication_failure`, `bad_config`,
   `insufficient_permissions`, `stopped`. Device availability is `last_seen` within the timeout,
   logged and broadcast on transitions only.
4. **Clause 6, tier test:** back the tier with a per-plugin checklist (`done`, `todo`, or
   `exempt` plus a comment). `verified` requires no `todo`.
5. **Consequences:** add the migration for the status choices and the backoff fields, folded
   into the manager-connection migration ADR-015 already requires. Add one allowlist scrubber
   shared by fixtures and diagnostics, and write-only credentials.

## Licensing

Everything above is a design pattern, re-implemented rather than copied. If code is ever lifted:

- Home Assistant core, NetBox, and Node-RED are Apache-2.0.
- `companion-module-base` and zigbee-herdsman-converters are MIT.
- Zigbee2MQTT is GPL-3.0.

All of these can be incorporated into AGPL-3.0-or-later code with attribution. The GitHub API
reported no SPDX license for the OpenRemote repository, so check its license file before reusing
any OpenRemote code. Only an enum name list is referenced here.
