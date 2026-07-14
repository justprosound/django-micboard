# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/).

## [Unreleased]

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
