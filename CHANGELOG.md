# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/).

## [Unreleased]

### Fixed

- The release publishing workflow serialised every version into one concurrency lane, so a
  stacked release could be discarded without publishing. A single global group holds only one
  pending run: with `2026.9.24.0` waiting on the publishing environment approval and
  `2026.9.24.1` queued behind it, dispatching `2026.9.24.2` cancelled `2026.9.24.1` before it
  claimed a runner, and that version was never published. The group is now keyed by version,
  so distinct releases publish on their own lanes while two runs for the same version still
  queue.

## [2026.9.24.2] - 2026-09-24

### Added

- `micboard.websockets.authorization` — `AuthorizationCache` and `CommandBudget`, which put a
  declared number on what one WebSocket connection may cost. Two new Django settings configure
  them: `MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS` (default 5, maximum 300) and
  `MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE` (default 60, maximum 6,000).

- `micboard.W002` and `micboard.W003` system checks, which report a WebSocket delivery mode a
  deployment has only half wired. Channels installed without an `ASGI_APPLICATION` accepts no
  handshake, and Channels without a `CHANNEL_LAYERS` backend discards every broadcast at debug
  level. Both were previously silent, so a deployment could believe it was pushing while every
  client was really still polling.

- Reverse-proxy guidance in the installation guide, covering what each delivery mode actually
  puts through a proxy, the `proxy_read_timeout` the nginx WebSocket block omitted (nginx
  defaults it to 60 seconds, which closes a healthy but quiet connection), and the equivalent
  Traefik `respondingTimeouts` and `forwardingTimeouts` configuration.

### Changed

- `MicboardConsumer` reuses one authorization decision for a bounded time to live instead of
  re-reading it from the database before every outbound frame. The guarantee is unchanged —
  the connection still fails closed when authentication or any joined route is revoked — but
  its cost is now bounded: a broadcast storm costs one query rather than one query per frame.
  Revocation takes effect within `MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS` (default 5)
  rather than on the very next frame; set it to `0` to restore per-frame re-reading.

- The inbound keepalive ping is metered per connection. It was the one lever a client had over
  the server's authorization work, and it was unthrottled. A connection that exceeds
  `MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE` is now closed with code `4429`.

### Removed

- **Breaking:** `MicboardConsumer.status_update`. Nothing in Micboard ever sent a
  `status_update` event, and its name shadowed `device_status_update`, which does have a
  producer — so a host wiring "status" was likely to pick the handler that would never fire.
  Use `device_status_update` for persisted hardware transitions and `api_health_update` for
  manufacturer API health.

- **Breaking:** the entire `micboard/static/micboard/js/` tree (13 files). No template in this
  package loaded any of it, and the endpoint its poll targeted (`/api/data/`) has no URL
  pattern. It also expected `chart-update` and `data-update` messages that the consumer never
  sends. It read as a working second front-end and described behaviour the package does not
  have. A host project that vendored these files should keep its own copy.

### Fixed

- A non-finite value in either WebSocket bound was not handled.
  `MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE` raised `OverflowError` on infinity, which would
  fail every handshake. `MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS` was quieter and worse:
  every comparison against NaN is false, so clamping collapsed it to `0` and silently
  restored the unbounded per-frame queries the setting exists to bound. Both now fall back to
  the shipped default.

### Commits

- chore: release 2026.9.24.1 (#277) (d41cc3c)
- refactor(ui): give browser poll cadence one owner outside the markup (#271) (701b05b)
- chore: release 2026.9.24.0 (#276) (47601a3)
- refactor: deepen the domain seams and correct the ADRs (#268) (cb301f3)
- chore(deps): update python docker tag to v3.14 (#275) (cbdfd1d)
- chore(deps): update github/codeql-action digest to 2892aa5 (#274) (61616a7)
- chore(deps): update postgres docker digest to 86c951e (#270) (9770ce3)
- feat(demo): add a read-only demonstration deployment (#269) (aeae07b)

## [2026.9.24.1] - 2026-09-24

### Added

- `micboard.services.settings.browser_refresh_service` — the one module that decides how often
  each live browser surface re-polls. Every browser update Micboard ships is delivered by
  short-polling over ordinary HTTP, so the refresh interval multiplied by open tabs is the
  whole request volume a deployment puts through its reverse proxy. Four new `MICBOARD_CONFIG`
  keys (`REFRESH_INTERVAL_ALERTS`, `REFRESH_INTERVAL_ASSIGNMENTS`, `REFRESH_INTERVAL_CHARGERS`
  and `REFRESH_INTERVAL_KIOSK_HEARTBEAT`) make that number reachable, each clamped to the 2 to
  3,600 second bounds that already governed a stored `DisplayWall.refresh_interval_seconds`.

### Changed

- The alert, assignment and charger pages read their poll interval from settings instead of
  declaring it in markup. Behaviour is unchanged at the shipped defaults (5s, 5s and 10s).

### Fixed

- A non-finite or fractional browser refresh interval in `MICBOARD_CONFIG` was not handled.
  `int(float("inf"))` raises `OverflowError`, which failed the request rather than falling
  back, and a fractional value was silently truncated — `0.5` became `0` and then clamped up
  to the floor, so a typo produced the fastest poll the bounds allow. Both now fall back to
  the shipped default. Numeric strings and already-whole floats are still used as written.

### Commits

- refactor(ui): give browser poll cadence one owner outside the markup (#271) (701b05b)
- chore: release 2026.9.24.0 (#276) (47601a3)
- refactor: deepen the domain seams and correct the ADRs (#268) (cb301f3)
- chore(deps): update python docker tag to v3.14 (#275) (cbdfd1d)
- chore(deps): update github/codeql-action digest to 2892aa5 (#274) (61616a7)
- chore(deps): update postgres docker digest to 86c951e (#270) (9770ce3)
- feat(demo): add a read-only demonstration deployment (#269) (aeae07b)

## [2026.9.24.0] - 2026-09-24

### Added

- A read-only demonstration deployment. `micboard/fixtures/demo.json` holds the structural
  demo dataset (a Shure ULXD4Q receiver, its channels, four transmitters, a monitoring group,
  and performer assignments), and the new `seed_demo_data` command loads it, writes telemetry
  relative to the current time, and manages a `demo` staff account that holds only `view_`
  permissions. The account is created only when `MICBOARD_DEMO_PASSWORD` is set, so a
  deployment cannot publish a login with a default password. A root `Dockerfile` and a `demo`
  extra (gunicorn, whitenoise, dj-database-url, psycopg) build the image; see
  [the deployment guide](docs/demo-deployment.md).
- `micboard.services.shared.access_policy.visible_to(model, *, user, using=None)` — the one
  predicate for "rows this user may see". It owns the dispatch between a model's own
  tenant-aware manager and the shared cascade, which five modules had each written out
  separately.

### Changed

- `ManufacturerPlugin.transform_transmitter_data` is now abstract. `DeviceUpdateService`
  persists through whichever plugin it is handed and calls that method for raw wireless-unit
  payloads — it uses the payload as-is when the transport already normalised it, and returns
  early when the payload is not a mapping — so a plugin without one was unusable on those
  paths. The contract now says so. Both shipped integrations already implement it.

- `services/sync/polling_api.py` builds its plugin through `build_manufacturer_plugin`
  instead of importing `ShurePlugin`, so no module outside `micboard/integrations/` constructs
  a vendor plugin directly. That module still gates managed-device polling on
  `ManufacturerAPIServer.Manufacturer.SHURE`, which is the only API-server protocol
  implemented; ADR-004 clause 9 records it as a permitted exception alongside the API-server
  connection surface and the admin connection checker.

### Removed

- **Breaking:** `MonitoringService.get_accessible_chargers` and
  `MonitoringService.get_accessible_display_walls`, which were one-line forwarders to
  `objects.for_user`. Call `visible_to(Charger, user=...)` or
  `visible_to(DisplayWall, user=...)` instead.

- **Breaking:** `micboard.services.monitoring.base_health_mixin` and its `HealthCheckMixin`.
  `BaseHTTPClient` overrode the mixin's `check_health` and `is_healthy`, and its 56-line
  `_parse_health_response` had no caller, so the transport inherited from a monitoring module to
  reach one formatting helper. That helper is now
  `micboard.services.common.base.client.standardize_health_response`, a module-level function
  beside its two callers.

- **Breaking:** `micboard.services.realtime.connection_service`. Its `mark_connected`,
  `mark_connecting`, `mark_error`, `mark_stopped` and `received_message` are now
  `RealTimeConnection.objects` queryset methods (`record_message` replaces `received_message`,
  and `reset_errors` and `mark_disconnected` join them), so one definition covers a single
  tracked row and a bulk admin selection alike. `connection_duration` and
  `time_since_last_message` are now the `connected_duration` and `time_since_last_message`
  properties on the model.

- **Breaking:** `TenantOptimizedManager` and the seven manager subclasses that extended it
  (`WirelessChassisManager`, `WirelessUnitManager`, `ChargerManager`, `DisplayWallManager`,
  `RFChannelManager`, `PerformerManager`, `PerformerAssignmentManager`). Every model now exposes
  its queryset directly with `as_manager()`, so the thirty-five one-line forwarders are gone and
  the interface no longer has to be restated on two classes.

- **Breaking:** the queryset helpers with no caller anywhere in the package or its host project:
  `for_organization`, `for_campus`, `with_manufacturer`, `with_location`, `with_chassis` and
  `recently_seen` on `TenantOptimizedQuerySet`, and `active`, `inactive`, `by_status`, `by_role`,
  `by_manufacturer`, `with_channels`, `by_type`, `low_battery`, `by_location`, `with_inventory`,
  `with_sections`, `by_wall`, `with_chargers`, `by_direction`, `receive_links`, `send_links`,
  `with_wireless_unit`, `with_assignments`, `by_monitoring_group`, `with_performer_and_unit` and
  `needing_alerts` on the model querysets. `for_user`, `for_site`, `for_memberships`,
  `supports_membership_scope` and `PerformerAssignment.objects.active()` are the ones that had
  readers, and they remain. Each deleted helper was a one-line `filter`, `select_related` or
  `prefetch_related` a caller can write inline.

- **Breaking:** the seven HTMX partial endpoints — `micboard:channel_card_partial`,
  `micboard:charger_slot_partial`, `micboard:wall_section_partial`, `micboard:alert_row_partial`,
  `micboard:assignment_row_partial`, `micboard:charger_grid_partial` and
  `micboard:device_tiles_partial` — along with `micboard/views/partials.py` and the five templates
  only it rendered. No template or script in this package ever requested them, and three
  duplicated a live route (`ChargerGridView`, `assignment_rows`, `KioskContentView`). A host that
  polled one of these URLs should move to the corresponding domain route.

- `MonitoringService.get_accessible_channels` and `MonitoringService.get_accessible_charger_slots`,
  which existed only to scope the two deleted channel and charger-slot fragments.

### Fixed

- `visible_to(model, user=..., using=alias)` read the caller's tenant boundary from the wrong
  database. Answering the question in MSP mode takes two reads: `for_user` materialises the
  active organization memberships as it builds the queryset, and the alias was applied only to
  the finished queryset afterwards. A multi-database host therefore narrowed one database's
  rows by another database's memberships. The database is now bound before the tenant boundary
  is applied. Single-database deployments were unaffected.

- **Hardening:** alert delivery authorized the recipient against the wireless unit's tenant
  boundary, reached through `base_chassis`, while reading an alert authorizes against the alert
  row's own boundary, reached through `channel__chassis`. The two disagree whenever a unit is
  assigned to a channel on another chassis, which would attach one organization's device state
  to another organization's channel — visible to that organization's members and invisible to
  the recipient it was written for. `AlertFanoutService.recipient_has_alert_scope` (previously
  `recipient_has_unit_scope`) now requires the recipient to hold both boundaries.

  No shipped code creates that state: `DeviceUpdateService` is the only production writer of
  `assigned_resource` and sets `base_chassis` to the same chassis in the same call, the two
  admin form layers reject it, and the demo fixture is consistent. It is reachable only through
  a host project's direct ORM writes, a hand-written fixture, a data migration, or the shell —
  all plausible for a reusable app, none of them a live leak today. There is still no model
  `clean` or database constraint preventing it, which is the root cause this only defends
  against.

- Bulk chassis deletion from the admin changelist registered its discovery reconciliation,
  locked the selected rows, and suppressed the per-row delete hooks *before* running the
  authorization check that could reject the request. Only the surrounding transaction's rollback
  undid that work. `ChassisBulkDeleteService` now owns the sequence with authorization first, and
  rejects a selection containing any row the caller may not delete rather than applying it in
  part. The admin action is a three-line call, so `suppress_chassis_delete_hooks` no longer has a
  presentation-layer caller (ADR-002 clause 4).

- Marking a realtime connection connected from the admin changelist left a stale
  `disconnected_at` and a non-zero `reconnect_attempts` behind. The action wrote five of the
  seven fields the subscription runner writes, so the same state had two spellings and the
  changelist produced a row that claimed to be connected and disconnected at once. Every
  transition now has one definition on `RealTimeConnectionQuerySet`, reached by both the runner
  and the admin.

## [2026.9.23.0] - 2026-09-23

### Changed

- **Breaking:** the `sse_subscribe` and `websocket_subscribe` management commands are replaced by
  a single `realtime_subscribe --manufacturer <code>`, and the `start_sse_subscriptions` and
  `start_shure_websocket_subscriptions` Huey entry points by `start_realtime_subscriptions`. The
  transport was never an operator's choice — an integration streams over exactly one — so the
  runner now reads it from the plugin. `ManufacturerPlugin` gains two abstract members,
  `realtime_transport` and `subscribe_to_chassis(chassis, callback)`, and loses the
  non-abstract `connect_and_subscribe`; third-party plugins must implement both. Connection setup,
  authentication, framing, and cleanup now live entirely inside the integration package, so no
  orchestration code imports a vendor module or branches on a manufacturer code.

- `build_device_https_url` moved from `micboard.services.realtime.subscription_supervisor` to
  `micboard.services.common.base.utils`, so an integration can build a per-device origin without
  depending on the realtime orchestration layer.

- There is now one way to obtain a manufacturer plugin. `PluginRegistry` and
  `get_manufacturer_plugin_instance` are removed in favour of
  `micboard.services.common.base.plugin.build_manufacturer_plugin(manufacturer)`, which
  resolves the class once per process and raises `ModuleNotFoundError`/`ImportError` when a
  manufacturer has no shipped integration. Callers that previously had to branch on a `None`
  now handle one failure shape. `clear_plugin_cache()` replaces `PluginRegistry.clear_cache()`,
  and the unused `get_all_active_plugins()` is gone.

- Validating a `ManufacturerConfiguration` whose `code` has no `Manufacturer` row is now
  reported as an error rather than passing. Nothing polls such a configuration, so the previous
  result was a false pass.

### Fixed

- `poll_manufacturer_devices` evaluated post-poll alerts and logged `Polling task complete`
  even when the sync returned `success=False`, so a failed poll ran its success path against
  stale inventory. The task now reports the failure and returns without evaluating alerts.
- `record_message()` resurrected a stopped realtime connection. Stopping a row from the admin
  does not tear down a live subscription, so a late callback put it back to `connected` and
  cleared `disconnected_at`. Error and disconnected rows are still recovered; a deliberate
  stop is not.
- Bulk chassis deletion authorized the selection before locking the rows, so a concurrent
  location change could move a chassis out of the caller's tenant scope in between, and the
  delete used the identifiers the caller supplied rather than the locked rows. Scope is now
  re-checked while the locks are held, and only the locked primary keys are deleted.
- A shipped integration whose own dependency was missing was reported as
  `Plugin not found`. `get_manufacturer_plugin` treated any `ModuleNotFoundError` during
  import as "this integration does not exist", including one raised inside the plugin module
  itself, so a missing vendor package sent an operator looking for an uninstalled
  integration. Only a genuinely absent integration module is swallowed now.
- A realtime subscription cancelled while its connection tracking was still being created
  left the row in `connecting`. The round had marked it connecting inside the worker thread
  but did not yet hold it, so the cleanup path skipped it. Closing now resolves the row by
  chassis when the handle is missing.
- An empty chassis inventory acquired the realtime transport lease before discovering there
  was no work. Leases expire rather than being released, so the next run was skipped for the
  whole lease timeout. Eligibility is now checked with a query that does not advance the fair
  rotation cursor, before the lease is taken.
- `poll_devices` printed a successful summary for a failed poll. `sync_devices_for_manufacturer`
  reports expected failures — a missing integration, an inventory over its configured limit, a
  manufacturer deactivated mid-poll — in the returned result rather than by raising, and the
  command never read `result.success`, so an operator saw
  `Success: 0 created, 0 updated, 0 examined` and an exit status of zero.

- A poll whose manufacturer was deactivated during vendor I/O left no audit row. The wrapper
  reloaded the manufacturer with an `is_active` filter before recording the audit, so the
  reload returned nothing and the durable record of a poll that had already reached the vendor
  was skipped.

- A manufacturer plugin whose constructor failed for a reason other than a missing module
  escaped `sync_devices_for_manufacturer` as an exception, skipping the audit, and a
  configuration error such as a missing vendor password was reported as `Plugin not found`.
  Initialization failures now return a redacted failed result that is distinguishable from an
  absent integration.

- A realtime connection row stayed in `connecting` or `connected` after its subscription ended.
  Supervisor rotation and shutdown cancel the subscription task, and `asyncio.CancelledError`
  is a `BaseException`, so the round's `except Exception` never saw it; a stream that returned
  on its own was not closed either. Both paths now mark the connection stopped, while a genuine
  failure keeps its error state.

## [2026.9.21.2] - 2026-09-21

### Fixed

- `collectstatic` failed outright under `ManifestStaticFilesStorage`, the standard
  production choice, because `micboard/static/micboard/css/theme.css` referenced IBM Plex
  font files that were never vendored: the stylesheet was compiled with the whole
  `@ibm/plex` package imported, emitting 424 `@font-face` blocks across nine families with
  `url()` paths pointing outside the package. Only IBM Plex Sans and Mono are ever applied
  by a rule, so the 202 blocks for the other seven families are removed and the two real
  families now load Latin-1 `woff2` subsets vendored under
  `micboard/static/micboard/vendor/ibm-plex/`, alongside the SIL Open Font License. The
  stylesheet drops from 458 KB to 285 KB (#261).

### Changed

- ci: `docs:`- and `ci:`-prefixed commits on `main` no longer open a release pull request.
  Neither can change the distributed package — `docs/` and the workflows are pruned from the
  wheel — so they were cutting releases whose only difference was the version number. Their
  CHANGELOG entries wait for the next release that ships code.
- ci: `deploy-docs` also runs on `workflow_dispatch`. A merge performed with `GITHUB_TOKEN`,
  such as a bot-merged release pull request, does not raise the `push` event, so the
  documentation site could silently go unpublished for that commit; it can now be republished
  with `gh workflow run ci.yml --ref main`.

## [2026.9.21.1] - 2026-09-21

### Changed

- docs: migrate the documentation site from MkDocs + Material + `mkdocstrings` to Astro
  Starlight (#161). Pages stay authored as plain Markdown in `docs/`; search is now offline
  (Pagefind); `just docs` builds the static site into `site/` and `just serve-docs` serves it
  on port 9000. See [ADR-013](docs/adr/013-documentation-platform-starlight.md).
- docs: replace build-time `mkdocstrings` autodoc with `scripts/generate_api_docs.py`, which
  extracts Google-style docstrings statically with Griffe into committed Markdown under
  `docs/api/reference/`. The documentation build no longer loads Django settings, and the
  reference now covers the model domains, service layer, management commands, WebSocket
  consumers, and exception hierarchy.
- build: the documentation toolchain moved from the `docs` Python extra (MkDocs) to
  `package.json` (Astro Starlight); the `docs` extra now holds only the docstring extractor
  (`griffelib`) and `PyYAML`. Building the docs requires Node and npm in addition to `uv`.

### Added

- ci: the `build-docs` job now verifies generated-reference freshness, page coverage, internal
  link and anchor integrity, and runs a Playwright suite covering offline search, brand
  rendering, and WCAG 2.1 AA compliance via axe-core.
- ci: a `deploy-docs` job publishes the built site to GitHub Pages from `main`, so the
  documentation is served at <https://justprosound.github.io/django-micboard/>.
- `just docs-api`, `just docs-verify`, `just docs-frontmatter`, and `just docs-e2e` recipes.

### Removed

- `mkdocs.yml`, `.readthedocs.yaml`, the exported `docs/requirements.txt` and its consistency
  check, and the MkDocs-specific `docs/stylesheets/extra.css`.

## [2026.9.21.0] - 2026-09-21

- docs: add frontmatter titles to every documentation page (#161) (#253) (c21bd81)
- chore(deps): update dependency astral-sh/uv to v0.12.16 (#251) (7f9299c)
- chore(deps): update dependency uv to v0.12.16 (#250) (76c7061)
- chore(deps): update codecov/codecov-action action to v7.1.1 (#249) (18086ad)
- chore(deps): update dependency astral-sh/uv to v0.12.15 (#248) (618570b)
- chore(deps): update github/codeql-action digest to 1c5b675 (#247) (12f20db)
- chore(deps): update dependency uv to v0.12.14 (#246) (0ae29e4)
- chore(deps): update dependency astral-sh/uv to v0.12.14 (#245) (b26dd7a)
- chore(deps): update codecov/codecov-action action to v7.1.0 (#244) (54c7443)
- chore(deps): update github-actions (non-major) (#241) (18f116c)
- chore(deps): upgrade dependencies and lockfile (#243) (a5067af)
- chore(deps): update dependency uv to v0.12.12 (#240) (71e7c69)
- chore(deps): update dependency astral-sh/uv to v0.12.12 (#239) (6ca2fe0)
- chore(deps): lock file maintenance and docs requirements export (#238) (45af724)
- chore(deps): update dependency astral-sh/uv to v0.12.11 (#237) (ba106c0)
- chore(deps): update github/codeql-action digest to b96794f (#236) (ad19a26)
- chore(deps): update dependency astral-sh/uv to v0.12.8 (#231) (66cac0c)
- chore(deps): update dependency uv to v0.12.9 (#233) (d58ba5f)
- chore(deps): update dependency uv to v0.12.8 (#232) (920883d)
- chore(deps): lock file maintenance (#230) (dbf9c91)
- chore(deps): update github-actions (non-major) (#229) (acd9655)
- chore(deps): update dependency uv to v0.12.6 (#228) (07b6289)
- chore(deps): update dependency astral-sh/uv to v0.12.6 (#227) (bf00abf)
- chore(deps): update github/codeql-action digest to cdf488f (#226) (9e4fae7)
- chore(deps): lock file maintenance (#225) (6ff457b)
- docs: remove fossa status badges from readme (#224) (21c3de1)

## [2026.8.21.0] - 2026-08-21

- chore(ci): parallelize tests with pytest-xdist and auto-sync docs on bot PRs (#222) (b4416fc)
- chore(ci): remove warden AI review job and configuration (#221) (96f8a94)
- chore(deps): update dependency astral-sh/uv to v0.12.5 (#217) (971c555)
- chore(deps): update github/codeql-action digest to db488dd (#218) (bd63c1d)
- chore(deps): resolve dependency advisories and add bot auto-merge DX (#219) (3f59578)
- fix(release): stop dependency updates from triggering releases (#209) (27ab385)
- chore: release 2026.8.17.2 (#214) (ad4407b)
- chore(deps): update github-actions (non-major) (#213) (5f470b1)
- chore: release 2026.8.17.1 (#212) (37e64b5)
- chore(deps): update dependency wheel to v0.48.0 (#210) (7210d42)
- chore: release 2026.8.17.0 (#208) (511a08e)
- chore(deps): update dependency astral-sh/uv to v0.12.4 (#206) (6be0970)
- chore: release 2026.8.16.0 (#205) (b8eebd9)
- chore(deps): update getsentry/warden action to v0.45.0 (#204) (2cdbbc7)
- chore: release 2026.8.15.0 (#203) (bf98ef5)
- chore(deps): update getsentry/warden action to v0.44.0 (#202) (1a16658)

## [2026.8.17.2] - 2026-08-17

- chore(deps): update github-actions (non-major) (#213) (5f470b1)
- chore: release 2026.8.17.1 (#212) (37e64b5)
- chore(deps): update dependency wheel to v0.48.0 (#210) (7210d42)
- chore: release 2026.8.17.0 (#208) (511a08e)
- chore(deps): update dependency astral-sh/uv to v0.12.4 (#206) (6be0970)
- chore: release 2026.8.16.0 (#205) (b8eebd9)
- chore(deps): update getsentry/warden action to v0.45.0 (#204) (2cdbbc7)
- chore: release 2026.8.15.0 (#203) (bf98ef5)
- chore(deps): update getsentry/warden action to v0.44.0 (#202) (1a16658)

## [2026.8.17.1] - 2026-08-17

- chore(deps): update dependency wheel to v0.48.0 (#210) (7210d42)
- chore: release 2026.8.17.0 (#208) (511a08e)
- chore(deps): update dependency astral-sh/uv to v0.12.4 (#206) (6be0970)
- chore: release 2026.8.16.0 (#205) (b8eebd9)
- chore(deps): update getsentry/warden action to v0.45.0 (#204) (2cdbbc7)
- chore: release 2026.8.15.0 (#203) (bf98ef5)
- chore(deps): update getsentry/warden action to v0.44.0 (#202) (1a16658)

## [2026.8.17.0] - 2026-08-17

- chore(deps): update dependency astral-sh/uv to v0.12.4 (#206) (6be0970)
- chore: release 2026.8.16.0 (#205) (b8eebd9)
- chore(deps): update getsentry/warden action to v0.45.0 (#204) (2cdbbc7)
- chore: release 2026.8.15.0 (#203) (bf98ef5)
- chore(deps): update getsentry/warden action to v0.44.0 (#202) (1a16658)

## [2026.8.16.0] - 2026-08-16

- chore(deps): update getsentry/warden action to v0.45.0 (#204) (2cdbbc7)
- chore: release 2026.8.15.0 (#203) (bf98ef5)
- chore(deps): update getsentry/warden action to v0.44.0 (#202) (1a16658)

## [2026.8.15.0] - 2026-08-15

- chore(deps): update getsentry/warden action to v0.44.0 (#202) (1a16658)

## [2026.8.14.1] - 2026-08-14

- chore(deps): update astral-sh/setup-uv action to v10 (#200) (be77a12)

## [2026.8.14.0] - 2026-08-14

- fix(ci): enable Renovate automerge for digests and regenerate docs requirements (#199) (06059ae)
- chore(deps): update github/codeql-action digest to ff2f1c6 (#186) (6816534)
- chore(deps): update softprops/action-gh-release digest to 3d0d988 (#187) (a2cc732)

## [2026.8.13.2] - 2026-08-13

- fix(release): auto-approve PR-triggered CI for bot-created release PRs (#196) (cc5211e)

## [2026.8.13.1] - 2026-08-13

- fix(packaging): prune tests and dev directories from sdist (#194) (d272885)

## [2026.8.13.0] - 2026-08-13

### Added

- **Property-based testing**: Add `hypothesis` to development dependencies and include starter property tests for DTO validation to automatically generate and verify edge cases.
- **Mutation testing**: Add `mutmut` to development dependencies and introduce a weekly informational CI workflow to verify that tests successfully catch logic inversions and boundary errors.
- **Pull Request Template**: Add a pull request template to guide contributors in submitting clean, well-tested changes.

### Changed

- **Release automation**: Remove overlapping Release Drafter behavior, derive release notes
  deterministically from `[Unreleased]`, and automate preparation, TestPyPI verification, exact-SHA
  tag creation, and GitHub release assembly around one protected production approval; retry transient
  GitHub API failures when dispatching release validation, lock release preparation tools, restrict
  generated release pull requests to declared metadata files, and bind recovery artifacts to sealed
  source metadata.
- **Supported runtimes**: Support Python 3.13 and 3.14 with Django 5.2 LTS and 6.0, and reject model
  changes that omit migrations in CI.
- **Release package boundary**: Exclude development-only fuzzers from source distributions and
  wheels so package validation and publication use the same reusable-app boundary.
- **Dependency updates**: Enable auto-merge for Renovate dependency updates (digest-only and patch versions) to reduce maintainer overhead, with a 3-day stability delay on patch versions to guard against supply-chain attacks.
- **Contributor documentation**: Update `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` to explicitly state that the project is maintained by a single developer, setting expectations around response times.
- **Renovate dependency dashboard**: Auto-close the dependency dashboard issue when no updates remain, so stale dashboards do not accumulate; CodeRabbit issue enrichment stays enabled.

### Security

- **Dependency bumps**: Upgrade `gitpython` to 3.1.58, `cryptography` to 50.0.0, and `pyopenssl` to 26.4.0 in `uv.lock` (and regenerate `docs/requirements.txt`) to close all open GitPython and cryptography advisories, including git option injection, `git diff`/`rev-list --output` argument injection, `git config` section-name injection, clone/archive option denylist bypasses, and the PKCS#7 Bleichenbacher oracle. `pyopenssl` is bumped as a dependency requirement of `cryptography` 50.

## [26.07.18] - 2026-07-18

d4ffc65 - docs: Reorganize documentation into docs/ structure (#113) (bandwith)
b4ba461 - chore(deps): update getsentry/warden action to v0.41.0 (#112) (renovate[bot])
ce00949 - fix(release): Require verified signed tags (#111) (bandwith)
7752e8d - fix(release): Recover original published artifacts (#110) (bandwith)
8171466 - fix(release): Support isolated and same-day releases (#108) (bandwith)
e13b9b4 - fix(release): Use valid Syft release tag (#107) (bandwith)

### Fixed

- **Audio alert selection**: Include assignments configured only for low-audio alerts when
  selecting active performer assignments that need alert processing.
- **Documentation organization**: Move contributor and architecture references into the published
  documentation tree, repair internal links and SRED status records, and keep MkDocs tooling in the
  opt-in documentation dependency extra.
- **CI workflow consolidation**: Merge the `Documentation` workflow into `CI Quality Gates` as a
  `build-docs` job to share concurrency cancellation and eliminate a separate workflow file; skip
  the docs artifact upload on PR runs (validate only); reduce coverage artifact retention from 30
  to 7 days on non-main branches; remove the redundant `uv sync` from the `security` job since
  Bandit and `uv audit` operate on source and the lockfile respectively without needing packages
  installed.
- **Signed release identity**: Require a GitHub-verified maintainer-signed annotated tag for the
  exact release commit before PyPI or GitHub publication, consume that existing tag without
  workflow-scope escalation, and keep safe pre-publication retries possible.
- **Release recovery**: Add a least-privilege, approval-gated recovery workflow that verifies and
  reuses the original PyPI artifact after GitHub release assembly fails, and make distribution
  archives reproducible across safe retries with `SOURCE_DATE_EPOCH`.
- **Same-day releases**: Calculate collision-safe daily CalVer versions automatically using the `YY.MM.0D.MICRO` format, starting at `.0` and incrementing `.1`, `.2`, and later revisions as needed.
- **Release SBOM generation**: Pass Syft's v-prefixed release tag to the pinned Anchore action and
  document the GitHub Actions permissions required by automated release pull requests.
- **GitHub release assembly**: Pass explicit repository context to release CLI commands that run
  from the credential-isolated job without a source checkout.

## [26.07.15] - 2026-07-15

2370c40 - feat(release): Default to current CalVer (#105) (bandwith)
eaa480d - fix(release): Make publication atomic and retryable (#104) (bandwith)
20049d2 - ci(release): Harden package provenance (#103) (bandwith)
1f8bf42 - ci(security): Protect solo-maintainer releases (#101) (bandwith)
5b9ce4f - ref(security): Harden tenant, service, and release boundaries (#98) (bandwith)
552b3ff - ci: Upgrade GitHub Actions to Node 24 (#96) (bandwith)
a62ca87 - ref: Eliminate cyclic lifecycle dependencies (#93) (bandwith)
0d67373 - fix: harden tenant-safe operational workflows (#88) (bandwith)
255faff - chore(deps): update dependency pillow to v12.3.0 (#86) (renovate[bot])
1158b54 - chore(deps): update dependency pathspec to v1.1.1 (#85) (renovate[bot])
3bc86d9 - test: expand service-layer coverage (#87) (bandwith)
0354eab - chore(deps): update dependency idna to v3.18 (#84) (renovate[bot])
eabf7e7 - chore(deps): update dependency certifi to v2026.6.17 (#83) (renovate[bot])
d40559d - test: Add complete model factory catalog (#82) (bandwith)
5bcd630 - chore(deps): update uv to 0.11.28 (bandwith)
160d00e - chore(deps): update astral-sh/setup-uv action to v8.3.2 (#80) (renovate[bot])
8ad8dbc - feat: Harden public reusable app boundaries (#79) (bandwith)
266d7e2 - Merge pull request #50 from justprosound/renovate/charset-normalizer-3.x (bandwith)
794b0a3 - chore(deps): update dependency charset-normalizer to v3.4.9 (renovate[bot])
2fcc8a8 - chore: add FUNDING.yml (bandwith)
4545c5c - fix: Replace pip install with uv pip install per project policy (bandwith)
5544b7a - feat: Add Sentry Warden AI code review (bandwith)
d76756a - chore: Fix pre-commit config and cleanup repository (bandwith)
20fe57f - refactor(models): extract band plan constants and functions from device_specs.py into band_plans.py (bandwith)
b91ccfd - fix(mypy): resolve 11 type errors in changed service files (bandwith)
5846477 - refactor: migrate integrations/common/ to services/common/base/, fix bulk_sync_devices bug (bandwith)
b05db6e - refactor(hardware): decompose into domain services, add settings service, fix mypy errors (bandwith)
f84cc5a - docs: allow f-strings in logging per user preference (bandwith)
1dc0de8 - refactor(admin): split configuration_and_logging.py into configuration.py and activity_logs.py (bandwith)
2236a8f - chore: update uv.lock (bandwith)
db674a7 - refactor(core): decompose HardwareLifecycleManager into DeviceAPISyncService and DeviceHealthService (bandwith)
e867519 - refactor(discovery): decompose DiscoveryService into 5 single-responsibility services (bandwith)
abe7950 - refactor: remove manufacturers shim, GenericCRUDService, and dead code; fix logging f-strings (bandwith)
5797f7c - docs: add 4 product requirement documents aligned with ADRs and issues (bandwith)
33d95b2 - docs: add codebase context doc and 8 architecture decision records (bandwith)
95fc1fb - fix: remove stray bold formatting in AGENTS.md Agent skills section (bandwith)
a1185d3 - chore: scaffold Matt Pocock's engineering skills config (bandwith)
46db3ca - fix: register admin modules and fix import paths (bandwith)
f82e3d7 - chore: remove refactoring documentation artifacts (bandwith)
77d4823 - refactor: complete E402 lint compliance and fix import paths (bandwith)
257a058 - typing(integration_patterns): add casts and guards; fix mypy issues (bandwith)
c3a5fd0 - typing: improve GenericCRUDService generics; cast form fields & cleaned_data fixes (bandwith)
1cb22cf - chore(lint): add __init__ docstrings and minor import noqa (bandwith)
abcc436 - Merge release prep changes (bandwith)
82cdbda - feat: Add 12 specialized GitHub Copilot agents from awesome-copilot (bandwith)
52bfd00 - Improve test coverage with proper exclusions and pragma comments (bandwith)
5a11d46 - fix: code standards compliance - resolve ruff violations (bandwith)
4127ca8 - test(coverage): improve plugin_registry coverage to 97% (bandwith)
b5aa9da - massive work in progress (bandwith)
ce575a9 - refactor(release-prep): standardize configuration, improve docs, expand tests (bandwith)
434233d - massive work in progress (bandwith)
7176b3f - checkpoint: saving state before further changes (skipped linting due to environment issues) (bandwith)
c21977a - chore: finalize production release preparation (bandwith)
334b4f7 - docs: add Phase 4.2 completion summary (bandwith)
3605b56 - refactor: extract common HTTP client to eliminate duplication (bandwith)
edb45e3 - docs: consolidate documentation and update Docker for GT live testing (bandwith)
e65cd4e - cleanup: remove temporary files and consolidate documentation (bandwith)
ee4a09c - docs: add Phase 3 completion summary and developer quick reference (bandwith)
cb23ff7 - refactor: integrate lifecycle manager into polling services (Phase 3) (bandwith)
2bd55f6 - End of day commit: Updated README to clearly state major work in progress, added comprehensive tests, fixed various issues, and improved codebase structure (bandwith)
91da9f6 - Fix: Resolve pre-commit hook issues and mypy errors (bandwith)
25f566a - Complete Django Micboard refactor: Phase 1 modularization and Phase 2 core features (bandwith)
6d457d5 - Phase 1: Codebase audit and modularization refactor (bandwith)
3116436 - Fix signals/view issues: signatures, returns, cache guard, serialization (bandwith)
5320d67 - Refactor: Centralize Shure discovery and polling logic into signals; prepare API to emit discovery/refresh events (bandwith)
efcc7e5 - Remove Windows container artifacts and related scripts; keep README docs (bandwith)
89b947d - Add Windows demo image support: Dockerfile updates, CI workflow, installer handling and build helper (bandwith)
26ebeee - docs: admin layout + health, demo: windows dockerfile, entrypoint and conditional mock data; docker-compose restart policy (bandwith)
22cccf9 - Apply ruff formatting fixes (bandwith)
50fdaa7 - style: ruff format applied (bandwith)
1af4001 - chore: remove shim package and initial migration files (bandwith)
2346787 - docs: remove dev install and test step from documentation workflow (bandwith)
22ba8f6 - chore: add docs extra to pyproject and regenerate pinned requirements (bandwith)
a4bee37 - docs: simplify Read the Docs config — update build tools, move requirements and pre-install mkdocs-material (bandwith)
633a4fa - docs: refine Read the Docs config - move post_install and remove setuptools install (bandwith)
d1192e1 - docs: add API reference pages, MkDocs macros and refine docs build/config (bandwith)
f4d95bf - ci: make Coveralls upload non-fatal and add coverage.lcov to .gitignore (bandwith)
2ebfed1 - ci: cache matrix.json and make matrix generation resilient (bandwith)
04da1f1 - ci: show generated matrix and add safe fallback to generate-matrix.py (bandwith)
a830f5a - ci: add concurrency group and limit matrix parallelism to 2 (bandwith)
416fbe6 - ci: add concurrency group and limit matrix parallelism to 2 (bandwith)
11aad95 - style: apply ruff fixes to generate-matrix.py (bandwith)
0595fea - ci: standardize renovate condition quoting and use job-level test timeout (bandwith)
c046949 - chore: use pyproject.toml for pip-compile and consolidate requirements (bandwith)
f2431f2 - chore: tidy typing, tests and dev deps; add types-requests & mypy hook (bandwith)
d0e6db5 - Add multi-manufacturer plugin architecture (bandwith)
8892bb8 - Add timeout to pytest in CI to prevent hanging tests (bandwith)
4d531be - Fix CI workflow and dependencies (bandwith)
aacdec3 - chore: bump pre-commit hooks & ruff, replace bandit with mypy; tidy typing and tests (bandwith)
bb15441 - refactor: modernize model Meta typing, tidy docs/config, tests & entrypoint (bandwith)
2fd8669 - docs: Replace Codecov badge with Coveralls badge (bandwith)
9b27e63 - ci: Prevent workflows from running on Renovate branches (bandwith)
ed4562c - feat: Major feature update and refactoring (bandwith)
eee7a51 - docs: Add comprehensive AI agent instructions (bandwith)
2158d67 - docs: Consolidate documentation for automated hosting (bandwith)
c9fd5d8 - chore: Remove legacy test files and add missing docstrings (bandwith)
669fd7a - refactor: Split large files into organized packages for maintainability (bandwith)
10580dd - refactor: Create centralized serializers module for DRY principles (bandwith)
c0a90ca - feat: Django reusable app optimizations - admin enhancements, model improvements, API endpoints (bandwith)
bb968a2 - Django reusable app optimizations: settings validation, health checks, connection pooling, comprehensive signal handlers (bandwith)
397443d - Dev tooling: VS Code pytest runner + debug, pytest.ini, test migrations disabled; Shure API enrichment; remove splash assets; docs and tests updated (bandwith)
8b3fe04 - Refactor: Update device polling and model definitions (bandwith)
8e7a0ca - Major refactor: split views, modernize frontend, add templates & tests, update packaging (bandwith)
1ae650a - Switch license to AGPL v3: stronger author protection for SaaS usage (bandwith)
a7c2ce4 - Update repository URLs to justprosound organization (bandwith)
d961693 - first commit (bandwith)

### Added

- **Configuration API** (`micboard.services.settings.settings_service`): Unified settings service for host,
  feature-flag, and scoped database configuration
- **Architecture Documentation** (`micboard/ARCHITECTURE.md`): Comprehensive guide for developers on plugin architecture, multi-tenancy, and settings registry
- **Expanded Test Suite**: Tests for configuration module, plugin registry, and settings behavior
- **Focused `.env.example`**: Minimal example-project environment values with explicit API-server
  destination allowlisting
- **Enhanced README**: Detailed reusable app integration guide with plugin architecture examples
- **Comprehensive CONTRIBUTING.md**: Migration guidelines, code patterns, and development workflow documentation
- **Settings overrides diff view**: Admin view and template for scope-level configuration diffs
- **Native Huey integration**: Optional `huey.contrib.djhuey` task registration, Redis-backed
  host configuration, and an in-memory test backend
- **Access-control regression coverage**: User-scoped tests for alerts, assignments, chargers,
  display walls, kiosks, and nested resources
- **Reusable-app host coverage**: Core-only and custom-user host settings, migration integrity,
  package API, installed-wheel, query-budget, and WebSocket routing regression tests
- **Release verification**: Wheel-content validation and installed-wheel smoke testing
- **Dependency-change security gate**: Reject pull requests that introduce moderate-or-higher
  vulnerabilities across runtime, development, or unknown dependency scopes, and audit the full
  lockfile during push, pull-request, manual, and weekly CI runs
- **Signed release provenance**: Attest sealed wheel and source distributions with isolated
  Sigstore-backed GitHub build provenance before either package registry can publish them
- **Attested release SBOMs**: Generate an SPDX JSON bill of materials, bind it to the wheel and
  source archive with a Sigstore SBOM attestation, and ship it with the release checksums
- **PEP 740 package attestations**: Sign each registry upload with its environment-bound OIDC
  identity and publish the matching attestations alongside immutable GitHub release assets
- **NIST SSDF workflow evidence**: Map checked-in automation controls to the final SSDF 1.1
  practices while identifying SSDF 1.2 as a draft
- **Complete model factory catalog**: Domain-grouped Factory Boy adapters for every installed
  project model, with registry completeness, persistence, validation, optional-app, and
  swappable-user coverage
- **Service-layer regression coverage**: Direct Factory Boy-backed tests for discovery,
  deduplication, hardware lifecycle, locations, performers, alerts, and connections, with every
  targeted module at 90% coverage or higher
- **Import architecture gate**: Detect internal strongly connected components and reject
  model-to-service, model-to-task, service-to-task, and service-to-app dependency reversals
- **Performance contracts**: Query budgets for discovery batching, alert fanout, connection health,
  and manufacturer statistics
- **Admin workflow coverage**: Request-level smoke tests for tenant-scoped chassis, discovery
  approval, monitoring summaries, settings diffs, and HTMX channel fragments
- **Plugin development guide**: Live registry, shared transport, discovery, transformer,
  protocol-specific streaming, security, native Huey, and test contracts for new manufacturers
- **Maintenance workflow coverage**: Branch-focused tests for supported discovery, diagnostics,
  audit, settings, metrics, and realtime subscription commands and services
- **Poll-to-alert lifecycle coverage**: Exercise a native Huey task through persisted API-server
  credentials, normalized device telemetry, alert persistence, recipient delivery, replay
  deduplication, and cross-tenant rejection
- **Live monitoring fragments**: Add bounded HTMX row/grid refreshes for alerts, assignments,
  chargers, kiosks, and wall sections without history-wide polling counts
- **Receiver browsing coverage**: Add tenant-scoped, eager-loaded building, room, performer,
  priority, and device-role browsing through stable primary-key routes
- **Movement audit coverage**: Record manufacturer-detected chassis address changes as typed
  `DeviceMovementLog` events inside the serialized synchronization transaction
- **Polling audit coverage**: Persist bounded, secret-free `ServiceSyncLog` rows for supported
  manufacturer polling runs and expose the operational history through a read-only admin

### Changed

- **Solo-maintainer release protection**: Keep pull requests mandatory without an impossible
  self-approval requirement, preserve strict app-bound checks and signed linear history, require
  non-bypassable Code Owners approval at the production PyPI environment, and allow only squash
  merges
- **Organized GitHub Actions bootstrap**: Reuse one pinned uv/Python setup action across
  repository-controlled jobs, retain direct immutable setup in privileged jobs, enforce explicit
  job timeouts, expose one stable aggregate check for branch protection, assign valid code owners,
  and document the workflow trust boundaries
- **Observed release checks**: Dispatch CI, dependency-review, and documentation checks for the
  exact release head, wait for those workflow runs to succeed before merge, and separate Actions
  dispatch, repository write, and publication dispatch permissions across jobs
- **Verified release promotion**: Create release metadata through GitHub's signed commit API,
  build without workspace source overrides, verify TestPyPI digests before production approval,
  publish production from the same sealed workflow run, make named artifacts and draft releases
  safe to resume after job retries, and publish GitHub releases only after every integrity asset
  is attached
- **Automatic release CalVer**: Default blank release dispatches to the current UTC `YY.MM.0D.MICRO`
  while retaining a validated manual override for backfills
- **Hardened build dependencies**: Upgrade the exactly pinned build backend to setuptools 83.0.0
  and wheel 0.47.0, and lock Twine plus the PEP 740 signer through uv
- **Credential-safe workflow checkouts**: Disable persisted Git credentials for every read-only
  checkout, scope Warden provider secrets to its trusted review step, and request maintainer review
  for workflow, toolchain, lockfile, and agent-policy changes through CODEOWNERS
- **Tenant-safe chassis admin writes**: Validate final location ownership in request-bound forms,
  reject tenant-to-platform inventory escapes, and route admin creates and updates through the
  canonical organization-quota persistence seam
- **Bounded discovery approval plans**: Reject missing queue and hardware permissions before row
  locks, cap selected and same-address conflict scopes at 100 rows and per-type inventory locks at
  400 rows, and isolate inventory, target resolution, and conflict validation behind one plan
  interface
- **Canonical service exceptions**: Move settings, admin-audit setup, and realtime lease failures
  under `MicboardError`, reject future service-local exception roots, and translate unexpected API
  polling failures to a fixed secret-safe public error without flattening known transport metadata
- **Focused vendor clients**: Remove unverified test-only enrichment endpoints, Shure forwarding
  methods, and duplicate Sennheiser polling orchestration; production plugins continue to use the
  shared transport, discovery, transformation, and subscription contracts directly
- **Bounded vendor coordination**: Scope shared rate-limit locks to each remote API endpoint and
  reject Shure discovery updates whose merged remote and requested address list exceeds the global
  candidate limit
- **Protected release pipeline**: Prepare version and changelog changes on a release pull request,
  run the required CI, CodeQL, Bandit, package, and documentation checks before auto-merge, and
  publish the exact protected merge commit from environment-bound OIDC jobs
- **Least-privilege Warden token**: Reduce repository contents access from write to read while
  retaining only the pull-request and check scopes required for automated review
- **Explicit service imports**: Remove root package re-exports; import services from their owning
  domain modules
- **Explicit domain imports**: Remove unused domain-package service and view re-exports so package
  imports no longer eagerly load unrelated implementations
- **Explicit model imports**: Keep `micboard.models` for Django discovery only and import model
  classes from their defining domain modules
- **Validated service DTOs**: Replace mutable hardware-normalization and deduplication result
  containers with Pydantic DTOs, including a mutually exclusive deduplication outcome enum
- **Canonical chassis persistence**: Route manufacturer sync, discovery approval, promotion,
  imports, refresh, realtime updates, lifecycle creation, and regulatory repair through one
  `WirelessChassisWrite` DTO seam; remove private cross-service writers
- **Focused chassis ownership**: Split save lifecycle from band-plan detection and regulatory
  coverage, return typed band-plan results, and delete the mixed wireless-chassis service module
- **Settings persistence boundary**: Route bulk and manufacturer setting forms through one
  authorization-aware DTO service that performs scoped bulk definition lookup, typed
  serialization, upsert, and cache invalidation
- **Canonical settings ownership**: Move scoped lookup under the settings domain, make
  `SettingsService` the only production read/cache interface, keep deployment controls host-owned,
  and delete the shared registry path and feature-flag facade
- **Bounded live projections**: Cap dashboard and kiosk sections, chargers, and slots after tenant
  filtering; return typed truncation metadata and render explicit overflow notices
- **Bounded kiosk health**: Replace the unbounded connection-validation aggregator with a typed,
  tenant-scoped health projection capped at 16 sections, 32 chargers per section, and 32 slots per
  charger, including sentinel overflow metadata
- **Deep charger snapshots**: Return primitive nested Pydantic charger, slot, and performer DTOs;
  load assignments only for occupied serial numbers and skip the query for empty grids
- **Database-ranked assignments**: Select one deterministic active performer assignment per
  bounded wireless unit in SQL instead of materializing every candidate in Python
- **Indexed discovery approval**: Pre-index locked chassis and charger inventory by primary key,
  API identity, and serial identity so large approval batches avoid quadratic scans while
  preserving ambiguous matches for fail-closed validation
- **Organization device quotas**: Enforce finite chassis quotas under a locked organization row
  for creates, upsert create branches, and transfers into a different owner while allowing
  same-owner metadata updates at quota
- **Query-oriented services**: Split charger cache state, discovery candidate collection, and
  bounded HTTP transport enforcement from their orchestration services
- **Domain package cleanup**: Remove model package re-exports, dead pagination/sync/tenant helpers,
  the duplicate discovery-queue service, and the no-op manufacturer-default registry command path
- **Direct implementation calls**: Remove residual email and alert convenience functions,
  settings, metadata, lifecycle, regulatory, and routing forwarders, the optional-dependency
  alias, package-level feature-flag exports, the wildcard settings facade, and the no-op device
  status synchronization hook instead of retaining shims
- **Complexity enforcement**: Remove every remaining McCabe and branch-count exemption after
  simplifying the affected paths, so complexity rules now apply uniformly to production code
- **Hardware service cleanup**: Remove unused chassis activity/band-plan facades and dead battery,
  capability, and asynchronous status-sync methods; callers use lifecycle, specification, and
  band-plan implementations directly
- **Strict device-refresh plugins**: Call the required manufacturer plugin interface directly,
  removing optional-method compatibility branches while retaining fail-closed vendor errors
- **Explicit task imports**: Remove legacy task aliases and import task functions from their
  defining domain modules
- **Queued API-server checks**: Move admin-triggered vendor health checks to a hard-capped native
  Huey batch that revalidates the initiating user's permission in the worker
- **Fair, bounded alert fanout**: Rotate shared-cache cursors through eligible wireless units,
  active assignments, and active group recipients; cap assignment, recipient, and delivery work;
  and revalidate current user, group, assignment, and tenant scope before persistence and email
- **Bounded manufacturer polling**: Fail closed on oversized vendor inventories, bulk-index device
  identities instead of issuing per-device lookup queries, and chunk full-fleet realtime updates
- **Coalesced discovery dispatch**: Reconcile only after chassis identity changes, collapse
  manufacturer-sync batches to one post-commit request, and suppress duplicate Huey enqueues with
  a short fail-open shared-cache claim
- **Bounded charger polling**: Move native Huey charger work into a typed service, cap device,
  station, slot, and vendor-text processing, resume list-like inventories across cached pages,
  publish only full-cycle snapshots with a deterministic station prefix, deduplicate station
  requests, read health once, and revalidate that queued manufacturers remain active
- **Service surface cleanup**: Remove unused unscoped hardware, location, performer, and
  manufacturer query facades in favor of authenticated model managers and active service paths
- **Realtime event cleanup**: Remove the duplicate polling emitter and unused arbitrary error,
  sync-completion, and discovery-approval WebSocket event paths
- **pyproject.toml**: Fixed package data inclusion for fixtures and migrations
- **MANIFEST.in**: Improved to include `.env.example` and exclude workspace-only files
- **.gitignore**: Enhanced to prevent tracking of development artifacts and egg-info directories
- **GitHub pre-commit hooks**: Reject edits or deletions of migration history, validate that new
  migration files were generated by Django, and check model-to-migration drift for both app labels
- **Settings diff route**: Wire settings diff URL to the real view implementation
- **Supported runtimes**: Target Python 3.13 with Django 5.1, 5.2, and 6.0 CI coverage
- **GitHub Actions runtimes**: Upgrade checkout and artifact uploads to Node 24-based releases
- **Dependency management**: Standardize development, documentation, CI, and release commands on
  locked `uv` environments
- **HTTP integrations**: Use `httpx` consistently with typed retry, rate-limit, and API error
  handling
- **Bounded vendor transports**: Stream decoded HTTP and SSE data under configurable package
  ceilings, clamp retry delays, reject oversized JSON responses before parsing, discard oversized
  SSE lines and events without payload logging, and revoke queued or live vendor work when its
  manufacturer becomes inactive while preserving the explicit `poll_devices --force` override
- **Public project cleanup**: Remove private-host branding, obsolete queue guidance, and stale
  live-integration scripts
- **Operator tooling cleanup**: Remove destructive hard-coded seeding and vendor-specific scratch
  diagnostics while retaining supported admin auditing, discovery, health, import, and monitoring
  commands
- **Maintenance safeguards**: Bound CIDR expansion memory, fail closed outside regulatory-domain
  limits, propagate discovery batch failures, and preserve accurate structured sync metadata
- **Quality floor**: Raise enforced branch coverage from 49% to 95%, inventory every distributable
  Python module, and add behavioral contracts across services, models, commands, admin, and tasks
- **Discovery reconciliation**: Batch exclusivity checks and manufacturer API updates, preserve
  remote state while configured sources are incomplete, rotate shared budgets fairly across local
  inventory and configured scan definitions, and still remove database-proven cross-vendor
  ownership conflicts
- **Monitoring queries**: Prefetch alert recipients and preferences, eager-load unhealthy
  connection ownership, and aggregate connection statistics in two fixed queries
- **Settings access**: Route app startup and callers through `SettingsService`; raw
  `MICBOARD_CONFIG` reads are isolated to the settings service
- **Settings dependency boundaries**: Move package defaults and exact-scope policy into
  dependency-free modules so startup, models, and services share invariants without import cycles
- **Lifecycle boundaries**: Route model persistence events through explicit Django signal adapters
  while services own validation, derived state, audit, discovery, and post-commit behavior
- **Realtime update persistence**: Share one service between SSE, WebSocket, and command entry
  points, treating event payloads as partial snapshots that cannot mark unrelated devices offline
- **Realtime supervision**: Separate long-running SSE/WebSocket supervisors from polling, share a
  renewable singleton lease across commands and native Huey entrypoints, and hard-bound device and
  concurrency counts
- **Fair realtime supervision**: Rotate bounded inventory windows across rounds and restarts with a
  shared-cache cursor and time-slice long-lived subscriptions through a fixed worker pool so blocked
  or dropped connections cannot permanently starve later devices; reload eligible batches within
  the same supervisor lifetime with configurable rotation and reconnect delays
- **Realtime service boundaries**: Move SSE and Shure WebSocket subscription orchestration into
  typed services shared by thin native Huey tasks and foreground management commands
- **Shared realtime lifecycle**: Share eligible chassis selection, transform, persistence,
  primitive projection, broadcast, and secret-safe error handling between SSE and WebSocket while
  keeping transport connection and cleanup local
- **Post-poll alerts**: Rotate through a configurable, hard-capped set of assigned wireless units
  instead of scanning arbitrary manufacturer inventory or permanently starving later rows
- **Dependency automation**: Consolidate updates under Renovate; refresh locked Click, filelock,
  certifi, idna, Pillow, and platformdirs versions; ignore generated requirements exports; enforce
  lock/export consistency; and run documentation checks on dependency branches
- **Host-aware test users**: Shared pytest fixtures now use the host project's configured user
  model
- **Optional admin integrations**: Enable admin enhancements only when the host registers their
  Django applications
- **Settings presentation**: Separate tenant-visible diff and overview queries from configuration
  resolution, with a fixed query budget and fail-closed display allowlist
- **Settings administration**: Mask unknown values across standard admin views, disable raw
  import/export paths, and restrict row management and form choices to the user's tenant scope
- **Discovery approval**: Move queue promotion into an atomic service with target-model permission
  checks, stable row-lock ordering, bounded fallback identities, cross-model IP ownership,
  non-destructive updates, explicit charger validation, batch conflict detection, and one write per
  logical inventory target

### Fixed

- Apply the same tenant-role and platform-scope policy to queued API-server health checks and
  request-time admin actions, including active/staff/permission revalidation in the worker
- Enforce active-Site ownership when listing or submitting monitoring groups, including
  cross-organization superusers, and reject standalone admin relationships that combine RF
  channels and wireless units from different chassis
- Resolve regulatory status once per row, eager-load the effective RF channel, annotate explicit
  and country-fallback domains, and keep wireless-unit admin query counts constant as rows grow
- Eliminate duplicate lifecycle audit writes and use one alias-aware, redacting audit service for
  model transitions, manufacturer events, and EFIS imports
- Keep Sennheiser SSCv2 event streaming on the authenticated GET connection while sending control
  requests through a separate authenticated client to a validated same-origin control resource
- Remove per-refresh paginator counts from alert and assignment row fragments and reuse one
  annotated discovery-device existence result across both admin status columns
- Prevent manufacturer movement updates from requesting a nonexistent chassis `updated_at` field
- Deepen live DisplayWall rendering into one typed, tenant-scoped kiosk snapshot used by initial
  pages, periodic HTML fragments, JSON consumers, and wall-section partials while preserving a
  bounded query count
- Activate pinned HTMX on built-in browser pages, route kiosk refreshes to swappable HTML, restore
  template head extensions, and send kiosk heartbeats through Django's CSRF contract
- Render wall-section fragments from the current kiosk projection, with real section names,
  charger groups, performer status, and explicit empty states
- Propagate failures from either realtime subscription task while cancelling its sibling, and
  remove the remaining CodeQL warnings from branch and failure-path tests
- Configuration import consistency across app modules
- Whitespace issues in documentation and code examples
- Admin settings diff tests updated to validate masking and access control
- Preserve the public admin-audit command while moving registry selection and Unfold, media,
  search-depth, template, eager-loading, and live query checks into typed services; quick audits now
  skip HTTP query capture and audits no longer create a predictable persistent superuser account
- Restore wireless-unit admin registration and lifecycle/regulatory dispatch behavior
- Correct release provenance so tags and published artifacts target the release commit
- Enforce organization, campus, monitoring-group, and membership-role boundaries across model
  managers, assignment services, admin views, HTTP views, and monitoring data
- Route real-time updates only to authorized organization and campus channel groups, including
  collision-safe resolution for chassis and wireless-unit identifiers
- Bound charger, alert, and kiosk relationship loading to prevent per-row query growth
- Check discovery IP ownership before probing a candidate device
- Replace stale performer-assignment examples with the current scoped service API
- Stop normal Django ORM writes from emitting false deprecation warnings for required model
  lifecycle hooks, and fail tests on future deprecation warnings
- Correct alert preference field lookups so battery, signal, and audio notifications are emitted
- Prevent persistent alert-fanout truncation from pinning work to one unit or alert class by
  advancing the unit cursor after each attempt and alternating offline/transmitter priority
- Treat connected rows without a heartbeat as unhealthy and remove manufacturer-dependent query
  growth from connection statistics
- Validate hardware transitions from the locked database row and support chassis without an
  `updated_at` field
- Reconcile imported online devices through provisioning and roll back the complete import when
  any lifecycle transition is rejected
- Require a building hierarchy when creating locations, reject cross-building rooms, serialize
  duplicate checks for building-level locations, and prevent stale callers from restoring old data
- Preserve managed IPv4 and IPv6 chassis addresses when reconciling discovery candidates
- Restore pending-alert action routes, current hardware labels, and owner-scoped state transitions
- Prevent tenant-scoped settings diff and overview views from exposing foreign organization, site,
  or manufacturer overrides and remove diff per-definition query growth
- Prevent discovery approval from reading nonexistent queue fields or creating chargers without
  the required location
- Keep core admin changelists usable when optional admin packages are installed but not configured
- Preserve stable poll result keys and deterministic wireless-unit slot assignment across process
  restarts
- Fail manufacturer configuration validation when its plugin cannot be imported, and never run
  discovery network work inline when native Huey is unavailable or rejects a task
- Accept built-in vendor transformer identifiers, transition responding discovered hardware through
  valid lifecycle states, and skip offline reconciliation for incomplete authoritative snapshots
- Group queryset deletion callbacks and suppress obsolete discovery work during manufacturer
  cascades
- Require change permission for every mutating admin action and for discovery queue transitions
- Scope managed-device polling by API-server manufacturer and location before transport, preserve
  embedded channel telemetry without double transformation, normalize nullable transmitter values,
  and dispatch alerts only to their owning user's email address
- Keep test factories isolated from manufacturer discovery APIs while retaining explicit lifecycle
  coverage for production task submission
- Keep discovery approval fail-closed when queue records disagree about API IDs, serial numbers,
  roles, IP ownership, or explicit inventory links, while requiring only the target permission used
  by each create or update
- Mask unknown stored-setting definitions regardless of their name or scalar type
- Defer chassis broadcasts, manufacturer registration, task submission, and grouped delete cleanup
  until database commit, and run model lifecycle hooks exactly once through Django admin
- Replace stale discovery-admin fields and Django 6-incompatible one-argument `format_html()` calls,
  and provide reachable, secret-safe settings management pages
- Keep persisted manufacturer API-server polling and imports bound to each row's allowlisted URL
  and credential, with redacted failure state and deterministic client cleanup
- Keep lifecycle audit payloads JSON-safe when Django-native timestamps are recorded
- Restore platform-global and nested tenant-owned admin changelists in multi-site mode without
  widening ordinary staff access, and register the previously unreachable accessory admin
- Require explicit permission for the single-site browser update stream while preserving
  membership- and site-scoped WebSocket groups
- Move ORM work and blocking subscription handshakes off hardware event loops, and materialize
  public async query results before returning them to callers
- Format authenticated WebSocket origins correctly for IPv4 and IPv6 literals and reject invalid
  device ports before constructing a client
- Run the installed-wheel smoke contract from the local `just wheel` gate and mark its in-memory
  SQLite host explicitly as development-only
- Preserve the last complete charger dashboard snapshot while resumable inventory pages accumulate,
  retain the same vendor-order station prefix when a full cycle exceeds its station cap, and fail
  closed when any station request makes the cycle incomplete

### Removed

- **Settings package exports**: Import `settings`, `SettingsService`, and presentation services from
  their defining modules instead of a package-level convenience API
- **Compatibility exports**: Remove root model, service, task, exception, telemetry, rate-limiter,
  and discovery-sync aliases
- **Model convenience shims**: Use typed wireless-unit, chassis, and RF-channel domain services and
  template filters instead of deprecated model delegation methods
- **Cross-layer model delegates**: Call realtime, monitoring, organization, discovery, and plugin
  services directly from their owning application adapters
- **Obsolete runtime surfaces**: Delete destructive seeding and direct-probing commands, legacy
  polling/discovery orchestrators, unused compatibility facades, duplicate realtime emitters,
  private middleware, and their stale templates and guides
- **Dead monitoring surfaces**: Delete the duplicate charger-display route and template, the
  generic connection-validation and connection-state services, and test-only health aggregation
  and reconnect methods; supported kiosk and realtime services remain the only runtime paths
- **Test-only service APIs**: Delete unused lifecycle mutation/query helpers, metadata version
  accessors, unscoped chassis refresh, notification progress/system-email methods, health-state
  predicates, and the settings test-mode property; active callers use the canonical typed paths
- **Dead admin and polling surfaces**: Delete the unregistered wireless-unit inline and stop
  returning raw vendor device payloads from the persistence-only discovery polling service

### Security

- Update `cryptography` to 48.0.1 and `msgpack` to 1.2.1 to resolve
  `GHSA-537c-gmf6-5ccf` and `GHSA-6v7p-g79w-8964` in the locked dependency graph
- Enforce the same group-to-unit tenant invariant for performer-assignment updates, deletions, and
  deactivations, locking the authorization graph inside each mutation transaction
- Restrict optional sortable-admin writes to the request user's exact manageable queryset on the
  write database, apply reorder batches atomically, and disable globally ranked page-move actions
- Enforce MSP `viewer`, `operator`, `admin`, and `owner` roles at generic admin, bulk-action,
  related-widget, settings-management, and queued chassis-refresh mutation boundaries; reserve
  host-wide catalog writes for unrestricted platform superusers
- Remove the stale trusted-HTML wall-section rendering path and autoescape section, charger, and
  performer data in the HTMX fragment
- Clarified that `.env` files should never be committed (already in `.gitignore`)
- Added reminder in CONTRIBUTING.md about AGPL licensing requirements for production use
- Enforce monitoring-group scope on charger, kiosk, alert, performer-assignment, and HTMX lookup
  surfaces
- Require authenticated POST requests for kiosk heartbeat mutation and admin user promotion
- Require owner or superuser scope plus CSRF-protected POST requests for alert acknowledgement and
  resolution, and escape vendor channel snapshots in alert details
- Require HTTPS and certificate verification for authenticated manufacturer clients; private
  certificate authorities use the standard `SSL_CERT_FILE` or `SSL_CERT_DIR` trust configuration
- Redact API keys and subscription handshake identifiers from integration logs, and hardware
  identities and private network addresses from deduplication and probe logs
- Sanitize sortable payload failures and Sennheiser/Shure stream exception tracebacks so injected
  primary keys, callback messages, transport errors, and subscription failures cannot forge logs
  or disclose secrets
- Make activity and service-sync admin history strictly view-only, derive activity actor links and
  search fields from the configured user model, and correct live sync/status badge choices
- Detect snake, kebab, spaced, and camel-case credential keys before metadata key truncation;
  restore masked list secrets by stable identity and reject ambiguous or missing originals
- Serialize polling and import identity reads and writes behind one database lock, canonicalize
  valid MAC addresses, discard invalid MAC placeholders, and fail closed on cross-manufacturer
  serial, MAC, or occupied-IP conflicts in both live and dry-run imports
- Keep raw realtime event payloads and transport/cache exception details out of command and worker
  output
- Centralize secret-safe exception metadata so traceback context remains useful without rendering
  vendor payloads, credentials, private addresses, or forged log lines
- Pin GitHub Actions to immutable commits and keep coverage enforcement and reports self-contained
- Revalidate WebSocket authentication and current route membership immediately before every
  outbound event, including pong replies to client pings, and close revoked connections after
  discarding groups
- Build release artifacts without write or OIDC permissions, seal them with a SHA-256 manifest,
  verify the manifest in isolated publisher jobs, and publish through native `uv` trusted
  publishing with least-privilege permissions
- Treat incomplete local inventory, configured scan definitions, CIDR/FQDN expansion, and remote
  discovery payloads as non-authoritative for removals while still clearing database-proven
  cross-manufacturer conflicts
- Fail closed for unsupported or tenantless resources in MSP mode and prevent cross-tenant
  WebSocket subscription or broadcast leakage
- Scope stored settings overrides to active, internally consistent organization/campus memberships
  and visible managed manufacturers
- Honor restricted-superuser tenant memberships across monitoring topology, alert mutations, and
  performer-assignment choices when cross-organization access is disabled
- Disable generic admin import and export routes until request-aware resources can prove tenant
  scoping for every transferred row
- Scope charger and RF-channel admin inline choices to the current tenant, and reject forged
  cross-tenant or cross-chassis relationships during formset validation
- Refuse same-version release retries unless the current main commit is the exact release-metadata
  commit, preventing newer code from being published under previously prepared metadata

### Documentation

- Reusable app integration guide in README.md
- Migration safety and lifecycle documentation
- Plugin architecture and settings registry patterns explained
- Development workflow and commit message guidelines
- Management-command and plugin examples now match the installed public APIs

## [25.01.15] - 2026-01-15

### Added

- Initial beta release with multi-manufacturer support
- Device discovery and lifecycle management
- Alerting and performer assignment
- Real-time telemetry via WebSockets/SSE
- Multi-tenant support framework
- Settings registry with scope resolution
- Plugin architecture for manufacturer integration
