---
title: "ADR-016: Connection Health, Backoff, and Redaction"
---
**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Project team

## Context

ADR-015 defines what a plugin is. This ADR defines how its connections behave, borrowing
patterns from mature open-source integration hubs: Home Assistant, Bitfocus Companion, Node-RED,
and Zigbee2MQTT. The survey is in `docs/research/integration-hub-patterns.md`.

The current behaviour has gaps that get worse as vendors are added:

- `CircuitBreaker` keeps its failure count in process memory, so each Huey worker backs off on
  its own.
- A wrong password is retried until a Device Manager account locks.
- The persisted connection has a single `error` status, so a dead network and a bad credential
  look the same.
- Secrets are hidden by matching substrings in field names, which misses names it has not seen.

## Decision

1. **Typed unavailability.** A plugin raises `TargetUnavailable(retry_after=...)` when a target
   cannot be reached. Orchestration owns retry: it stores `consecutive_failures` and
   `next_attempt_at` on the target's row and backs off by `min(base * 2**n, cap)` plus jitter.
   `CircuitBreaker` is removed.
2. **Spread polls.** Each target's poll time gets a random offset, so targets don't all poll at
   the same moment.
3. **An authentication failure stops polling** until an operator saves new credentials.
4. **Online state** has one definition (refined 2026-10-16, [#374](https://github.com/justprosound/django-micboard/issues/374): **liveness**, meaning any traffic, is separate from **meter freshness**, meaning the age of the last meter sample per channel; a live connection with stale meters is its own state): a target is online if it was seen within a timeout
   derived from its `PluginTraits`, and any traffic counts as seen. Only online/offline
   transitions are logged and broadcast.
5. **Unchanged state is not re-broadcast.** If a target's new DTO equals the previous one,
   nothing is sent.
6. **Session limits** are enforced in the realtime process by a per-target semaphore sized from
   `PluginTraits.session_limit`.
7. **Credentials are write-only.** The API and admin return `has_password`, never the value.
   A test walks every serializer and fails on any credential field.
8. **Connection status categories:** `ok`, `connecting`, `disconnected`, `unreachable`,
   `auth_failed`, `bad_config`, and `unknown_error`. Existing `error` rows migrate to
   `unknown_error`.
9. **Diagnostics are allowlist-scrubbed.** Per-connection diagnostics, captured fixtures, and
   live-lane output all pass through the one allowlist scrubber. It replaces the substring
   denylist in `micboard/serializers/v1/discovery.py`.
10. **The quality checklist backs the tier.** Each plugin ships `quality.yaml`, listing every
    requirement as `done`, `todo`, or `exempt`. A plugin is *verified* only when no entry is
    `todo` and captured fixtures exist, and the tier test enforces both.
11. **An operator's "refresh now" is debounced** per target, so repeated requests queue one
    poll.
12. **Write exceptions are named, never inferred.** The read-only policy is default-deny. A plugin
    may list an exact write it needs, with a test that the guard admits that write and nothing
    near it. The only exception so far is Shure's `SET <channel> METER_RATE <digits>`, which
    turns on metering. A session that sent it always sends `METER_RATE 0` on clean shutdown,
    and QLX-D never gets it, because its firmware locks up if a metering client disappears.
    A value being null never makes a message a read: Sennheiser triggers `identify` with one.

## Consequences

- One definition each of online, retry, and redaction serves every vendor. Plugins carry none
  of that logic.
- New fields for backoff state, and the status categories, need migrations through
  `django-safemigrate`.
- Removing `CircuitBreaker` updates every call site in the same change, with no shim.

## Alternatives considered

- **Keep `CircuitBreaker` and share its state through the cache.** Rejected: a database row is
  already the per-target record, survives restarts, and is visible in the admin.
- **Home Assistant's denylist redaction (`async_redact_data`).** Rejected in favour of the
  allowlist: a denylist leaks any secret under a name it doesn't list.
- **Zigbee2MQTT's per-field `exposes` declarations.** Skipped: the typed normalized DTOs already
  describe every field.
