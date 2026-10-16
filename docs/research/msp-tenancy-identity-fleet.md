---
title: "Research: Tenancy, Identity, and Fleet Operations in Open-Source MSP Platforms"
---
**Question** ([#357](https://github.com/justprosound/django-micboard/issues/357), part of
[#321](https://github.com/justprosound/django-micboard/issues/321)): how do open-source MSP and
enterprise platforms model tenancy, locations, RBAC, identity, fleet operations for edge
collectors, HA and data residency, and the product surface? Which of their patterns should
micboard adopt, adapt, or skip?

**Date:** 2026-10-16. All sources are public. Source links point at each project's default
branch or current documentation as read on that date, so line content may drift. Licenses were
read from each repository's license file.

**Target scale:** thousands of sites, many MSP tenants, and hundreds of thousands of RF devices
and units with live meters. The stack is Django, Postgres, Huey, Channels, and asyncio, and there
is one maintainer.

**Boundaries with sibling tickets:** edge-to-central transport, multicast crossing, and packaging
belong to [#354](https://github.com/justprosound/django-micboard/issues/354). What the edge
listener *is* belongs to [#355](https://github.com/justprosound/django-micboard/issues/355).
Telemetry storage and live fan-out belong to
[#356](https://github.com/justprosound/django-micboard/issues/356). This page covers who owns an
edge listener, how it is enrolled, authorized, observed, upgraded, and configured, and what the
data model needs for that.

## Summary

1. **Keep row-level tenancy in one database, and make it always on.** Every platform surveyed that
   serves MSPs from one install (NetBox, Grafana, OpenWISP) puts a tenant key on shared tables.
   None of them uses a schema or database per tenant. micboard already does this. The change is to
   stop treating tenancy as optional: one default organization and campus in single mode removes
   two of the three branches in `visibility.py`.
2. **Add one level above the customer and one level beside the campus.** NetBox nests
   `TenantGroup` above `Tenant`, and `Region` and `SiteGroup` above `Site`. micboard needs a
   **provider** organization (the MSP) above customer organizations, so that MSP staff get
   delegated administration without a membership in every customer. It also needs an optional
   **region** above campuses for grouping and residency. NetBox's main branch now stores these
   trees in Postgres `ltree`, not django-mptt.
3. **Grant roles on scopes. Don't grant permissions on rows.** NetBox constraints, Zabbix user
   groups on host groups, and Grafana org roles all attach a role to a container (tenant, group,
   org), never to each device. django-guardian's per-object rows don't fit hundreds of thousands
   of devices. Keep micboard's four roles, attach them to organization, region, or campus scopes,
   and keep monitoring groups as the narrowing layer for viewers and operators.
4. **Identity: allauth for per-tenant SSO, Knox for machines, an append-only audit log.** An MSP's
   customers each bring their own IdP. django-auth-adfs and mozilla-django-oidc take one IdP per
   deployment from settings. django-allauth stores one OIDC or SAML app per organization in the
   database and routes SAML by organization slug. Edge listeners and integrations become service
   principals with Knox tokens. SCIM waits until a customer asks for it.
5. **Fleet operations follow the Zabbix proxy and Mender pattern.** Enrolment uses a single-use
   token per campus and then pending approval. Each listener holds its own credential. It pulls
   versioned config, reports its version and health on every heartbeat, and the server stores
   the desired version and reports drift. Upgrades are pull-based container image tags, gated by
   a compatibility window like Zabbix's current, outdated, and unsupported proxy states. micboard
   doesn't run an OTA system.
6. **HA, DR, and residency live in the deployment, not the schema.** Use managed Postgres or
   CloudNativePG, with pgBackRest or WAL-G for point-in-time recovery. Data residency is one
   deployment *cell* per jurisdiction, each with its own database. micboard doesn't route
   tenants to databases inside one install.
7. **Product surface.** micboard keeps the DRF API and adds outgoing webhooks signed to the
   Standard Webhooks spec. Entitlements become counters checked in a service. The existing
   `max_devices` and `subscription_tier` fields are a start. White-labelling uses the Django Site
   per portal plus django-unfold's per-request logo callables.

## Recommendations

| # | Option (source) | License | Verdict | Change to micboard |
|---|---|---|---|---|
| 1 | NetBox Tenant / TenantGroup | Apache-2.0 | **Adapt** | Add `Organization.kind` (`provider`, `customer`) and `Organization.parent`, two levels deep, not a free tree. |
| 2 | NetBox Region / SiteGroup / Site / Location | Apache-2.0 | **Adapt** | Add an optional nested `Region` per organization. Campus stays micboard's physical site. Building, Room, and Location stay as they are. |
| 3 | NetBox `NestedLtreeGroupModel` (Postgres `ltree`) | Apache-2.0 | **Adapt** | Use `ltree` (or a materialized path) for `Region` only. Skip django-mptt, which NetBox has deprecated. |
| 4 | Always-on tenancy (Grafana orgs, NetBox tenancy) | AGPL-3.0, Apache-2.0 | **Adopt** | Single mode becomes one default organization and campus. Turn `Building.organization_id` and `campus_id` into real foreign keys. |
| 5 | django-tenants (schema per tenant) | MIT | Skip | Migrations per schema across many tenants cost too much for one maintainer. |
| 6 | django-multitenant (Citus row distribution) | MIT | Skip for now | Keep `organization_id` on hot tables so Citus stays possible later. |
| 7 | LibreNMS device groups and global roles | GPL-3.0 | Skip | No tenancy. Its dynamic groups resemble monitoring groups, and per-device grants do not scale. |
| 8 | Zabbix host-group permissions (Read-write, Read, Deny; strictest per group) | AGPL-3.0 | **Adapt** | Grants go to scopes. Inheritance runs down the tree. No Deny. |
| 9 | Grafana orgs, basic roles, service accounts | AGPL-3.0 | **Adapt** | Fixed code-defined roles with no custom roles. Service accounts are per organization. Map IdP groups to org roles as `org_mapping` does. |
| 10 | NetBox ObjectPermission with JSON constraints | Apache-2.0 | Skip as a model, keep the idea | Role bindings to a scope compile to `Q` objects in `visibility.py`, which is already a constraint compiler. |
| 11 | django-guardian object permissions | BSD-2-Clause | Skip for devices | Use it only for rare per-object shares, such as one dashboard, and only with direct foreign keys. |
| 12 | OpenWISP organizations, managers, and owners | BSD-3-Clause (users), GPL-3.0 (controller) | **Adopt** pattern | The owner can't be demoted by other admins. Shared objects use `organization=None`, and only superusers manage them. |
| 13 | django-auth-adfs | BSD-2-Clause | Keep for single-IdP installs | One `AUTH_ADFS` config per deployment. It can't serve many customer IdPs. |
| 14 | mozilla-django-oidc | MPL-2.0 | Skip | One provider from settings, the same limit as #13, plus a new license family. |
| 15 | django-allauth (OIDC, SAML per organization, MFA) | MIT | **Adopt** | One `SocialApp` per organization, with SAML at `/accounts/saml/<org-slug>/`. Add TOTP and passkeys for local accounts. |
| 16 | djangosaml2, python-social-auth | Apache-2.0, BSD-3-Clause | Skip | Settings-driven and one IdP each, already covered by #15. |
| 17 | django-scim2 | MIT | Defer | Add it when a customer needs deprovisioning faster than SSO login and JIT provisioning give. |
| 18 | Keycloak, authentik, Zitadel as a broker | Apache-2.0, MIT core, AGPL-3.0 | Skip | A second stateful service to run and upgrade. Customers can still point allauth at one. |
| 19 | django-rest-knox | MIT | **Adopt**, extend | Service principals per edge listener and integration. Add NetBox v2 token fields: description, last used, read-only, allowed IPs. |
| 20 | django-simple-history and django-auditlog | BSD-3-Clause, MIT | **Adapt** | Keep simple-history for model diffs. Add one append-only `AuditEvent` with tenant, actor, principal type, and action. Skip auditlog. |
| 21 | Zabbix proxy (active pull, offline buffer, proxy groups, version window) | AGPL-3.0 | **Adopt** pattern | Listener pulls versioned config. Supported, outdated, and unsupported version states. Optional failover pairs per campus. |
| 22 | Mender device auth (pending, accepted, rejected, preauthorized) | Apache-2.0 | **Adopt** pattern | Listener enrolment states, preauthorization by single-use token, and token renewal. |
| 23 | Mender, Balena, hawkBit OTA | Apache-2.0, Apache-2.0, EPL-2.0 | Skip | micboard ships a container. It records a desired image tag and leaves the pull to the host. |
| 24 | Balena fleet and device variables | Apache-2.0 | **Adopt** pattern | Organization defaults, then campus, then listener overrides, in one resolved config document. |
| 25 | Fleet/orbit enroll secrets and TUF updates | MIT core | **Adapt** | Enroll secret per scope, revocable. Skip TUF, because signed container images cover it. |
| 26 | Tailscale tagged auth keys, headscale | BSD-3-Clause | Optional, documented | Remote support access only. Never required for the data path. |
| 27 | OpenWISP controller auto-registration and config status | GPL-3.0 | **Adopt** pattern | Config status per listener: `modified`, `applied`, `error`. |
| 28 | Patroni, CloudNativePG, managed Postgres | MIT, Apache-2.0 | Document | Managed Postgres by default. CloudNativePG for Kubernetes self-hosting. micboard ships no HA code. |
| 29 | pgBackRest, WAL-G | MIT, Apache-2.0 | Document | PITR runbook and a restore drill. |
| 30 | Data residency per tenant | — | **Cells** | One deployment and database per jurisdiction. No in-app database routing per tenant. |
| 31 | NetBox event rules plus signed webhooks, Standard Webhooks | Apache-2.0 | **Adopt** | Webhook subscriptions per organization, sent by Huey, signed to the Standard Webhooks spec. |
| 32 | Svix server | MIT | Skip | Another service to run. Huey and a delivery table are enough. |
| 33 | Quotas and entitlements | — | **Adapt** existing | Keep `max_devices` and `subscription_tier`. Add an entitlement service and limits for listeners, campuses, and API tokens. |
| 34 | django-unfold per-request branding, Django Sites | MIT, BSD-3-Clause | **Adopt** | Branding comes from the Site or provider organization through unfold's `request` callables. |

## What micboard has today

- **Tenancy:** `Organization` and `Campus` live in the optional `micboard.multitenancy` app
  ([`micboard/multitenancy/models.py`](https://github.com/justprosound/django-micboard/blob/main/micboard/multitenancy/models.py)).
  `Organization` already carries `site`, `max_devices`, `subscription_tier`, `logo`, and
  `primary_color`. `Campus` carries an address and `timezone`. `OrganizationMembership` holds one
  role per user and organization (`viewer`, `operator`, `admin`, `owner`), optionally limited to
  one campus.
- **Location:** `Building` has a Django `Site` foreign key and plain integer `organization_id` and
  `campus_id` columns, not foreign keys, because the multitenancy app is optional. `Room`
  belongs to a building. `Location` belongs to a building and optionally a room
  ([`micboard/models/locations/structure.py`](https://github.com/justprosound/django-micboard/blob/main/micboard/models/locations/structure.py)).
- **Who may see what:**
  [`micboard/services/shared/visibility.py`](https://github.com/justprosound/django-micboard/blob/main/micboard/services/shared/visibility.py)
  (PR #285) intersects a tenant boundary with monitoring reach across three deployment modes
  (single, site, MSP). Ownership paths are declared in `micboard/models/base_managers.py` and fail
  closed. The Django Site is per process (`SITE_ID`), so a Site is a *portal or deployment
  partition*, not a physical place.
- **Identity:** the `standard` extra already installs django-rest-knox, django-auth-adfs,
  django-guardian, and django-unfold. The admin uses django-simple-history when it is installed.
  `ConfigurationAuditLog` records configuration changes.

## 1. Tenancy and location hierarchy

### NetBox

- **Source:** [tenancy](https://github.com/netbox-community/netbox/blob/main/docs/features/tenancy.md),
  [facilities](https://github.com/netbox-community/netbox/blob/main/docs/features/facilities.md),
  [region](https://github.com/netbox-community/netbox/blob/main/docs/models/dcim/region.md),
  [site group](https://github.com/netbox-community/netbox/blob/main/docs/models/dcim/sitegroup.md),
  [location](https://github.com/netbox-community/netbox/blob/main/docs/models/dcim/location.md),
  [nested group base models](https://github.com/netbox-community/netbox/blob/main/netbox/netbox/models/__init__.py).
  License Apache-2.0. Latest release is v4.7.3 (2026-10-13).
- **Model:** `TenantGroup` nests recursively, and `Tenant` belongs to an optional group. A tenant
  is assigned to sites, devices, prefixes, and so on, and each object has one tenant at most. The
  docs give the MSP case directly: "a managed services provider might create a tenant in NetBox to
  represent each of its customers". Location is a separate axis. `Region` (geographic) and
  `SiteGroup` (functional) both nest and both parent `Site`. "Sites which belong to a child group
  are also considered to be members of all its parent groups." `Location` nests inside a site
  ("a floor, room, cage"). Tenancy and geography are independent: a site has a region *and* a
  tenant.
- **Tree storage:** v4.7 base models include `NestedLtreeGroupModel`, "These models nest
  recursively using PostgreSQL ltree". The MPTT base is marked "Deprecated MPTT-backed nested group
  base, retained for backwards compatibility with plugins". A trigger maintains `sort_path` so
  renames cascade without the manual rebuild django-mptt needed.
- **Mapping:** TenantGroup maps to a provider organization, Tenant to Organization, Region to a new
  `Region`, Site to Campus, Location to Building and Room, and Device to Chassis. NetBox's tenant
  is an *attribute* that any object can carry. micboard derives the tenant from the location path
  (`base_managers.py`), which is stricter and better for isolation. Keep derivation.
- **Operational cost:** two small models and one Postgres extension (`ltree`, in core contrib).
- **Verdict: adapt.** Take the two-axis idea (customer tree versus geographic tree) and `ltree`
  for the one tree that needs depth. Keep the customer side to two fixed levels, provider and
  customer, so permission inheritance stays a single join.

### LibreNMS

- **Source:** [device groups](https://github.com/librenms/librenms/blob/master/doc/Extensions/Device-Groups.md),
  [authentication and roles](https://github.com/librenms/librenms/blob/master/doc/Extensions/Authentication.md),
  [distributed poller](https://github.com/librenms/librenms/blob/master/doc/Extensions/Distributed-Poller.md).
  License GPL-3.0, with exceptions for bundled components.
- **Model:** no tenant. Static and dynamic device groups are built from SQL rules. Built-in roles
  are `admin`, `global-read`, and `user`, and a `user` "must [be assigned] the device permissions
  or the port permissions". Distributed pollers coordinate through a shared Redis.
- **Mapping:** dynamic groups correspond to micboard's monitoring groups. Per-device grants are the
  pattern to avoid at this scale.
- **Verdict: skip.** It shows what a no-tenant monitoring tool looks like when MSPs adopt it:
  per-device grants that one maintainer can't manage.

### Zabbix

- **Source:** [permissions](https://www.zabbix.com/documentation/current/en/manual/config/users_and_usergroups/permissions),
  [user groups](https://www.zabbix.com/documentation/current/en/manual/config/users_and_usergroups/usergroup).
  License AGPL-3.0 (the repository's license file).
- **Model:** host groups nest by name (`Parent/Child`), and a super admin can push a parent's
  permission down to nested groups. Access "to host and template data" is granted "to user groups
  on the host/template group level only". Individual users can't be granted host access directly.
  The levels are Read-write, Read, and Deny. Deny wins, then the most permissive level, and "the
  strictest permission will be applied" when the same group appears twice. User *type* (User,
  Admin, Super admin) sets a ceiling that roles can only narrow.
- **Mapping:** host group maps to Region and Campus, user group to an IdP group, and user type to
  a deployment-wide flag such as provider staff.
- **Verdict: adapt.** Grants go only to containers and only through groups, which keeps the
  grant table small. Skip Deny: a role on a narrower scope is enough, and Deny makes
  `visibility.py` harder to reason about.

### Grafana

- **Source:** [organizations](https://github.com/grafana/grafana/blob/main/docs/sources/administration/organization-management/index.md),
  [roles and permissions](https://github.com/grafana/grafana/blob/main/docs/sources/administration/roles-and-permissions/_index.md),
  [RBAC](https://github.com/grafana/grafana/blob/main/docs/sources/administration/roles-and-permissions/access-control/_index.md),
  [teams](https://github.com/grafana/grafana/blob/main/docs/sources/administration/team-management/_index.md),
  [generic OAuth org mapping](https://github.com/grafana/grafana/blob/main/docs/sources/setup-grafana/configure-access/configure-authentication/generic-oauth/index.md).
  License AGPL-3.0. Fixed and custom RBAC roles, team sync, and SCIM are Enterprise or Cloud only.
- **Model:** an organization isolates "users and resources such as dashboards, annotations, and
  data sources", and gives "completely separate experiences, which look like multiple instances
  of Grafana, within a single instance". Users can belong to many orgs, with one basic role each
  (Viewer, Editor, Admin). Service accounts are "Isolate only", so they belong to one org. The
  table also marks authentication providers "Share only": every org uses the same IdP config.
  Generic OAuth maps IdP values to org roles with `org_mapping`
  (`<ExternalName>:<OrgIdOrName>:<Role>`), and "the highest of the two mapped roles" wins.
- **Mapping:** Grafana org maps to Organization, basic role to membership role, team to
  monitoring group, and service account to an edge listener or integration principal.
- **Verdict: adapt.** Copy three things: fixed code-defined roles, service accounts that belong
  to one tenant, and group-claim to org-role mapping. Fix the gap in Grafana OSS: MSP customers
  need *per-tenant* IdPs, which "Share only" can't provide (see section 3).

### OpenWISP (Django precedent)

- **Source:** [openwisp-users concepts](https://openwisp.io/docs/stable/users/user/basic-concepts.html),
  [openwisp-users](https://github.com/openwisp/openwisp-users) (BSD-3-Clause),
  [openwisp-controller](https://github.com/openwisp/openwisp-controller) (GPL-3.0).
- **Model:** a Django network controller for MSPs. "Each tenant can only see and interact with the
  data of their organizations" and shared objects. Membership has an `is_admin` flag ("Organization
  manager"), and non-managers see nothing in the admin "even if they are flagged as Staff
  users". The first manager becomes **owner**, and only superusers and the owner can change the
  owner. Shared objects have no organization ("Shared systemwide"), and only superusers manage them.
- **Verdict: adopt the owner rule and the shared-object convention.** micboard already has an
  `owner` role. It should also enforce that other admins can't demote or remove the owner, and
  that rows with `organization=None` (shared templates, regulatory domains) are superuser-managed.

### Database-level tenancy libraries

- **django-tenants** ([README](https://github.com/django-tenants/django-tenants), MIT) gives each
  tenant its own Postgres schema. Every migration then runs once per schema. With many MSP
  tenants that is slow, fragile, and hard to roll back for one maintainer. **Skip.**
- **django-multitenant** ([README](https://github.com/citusdata/django-multitenant), MIT) is for
  "all tenants share the same table(s)" and "assumes that all the tenant relates models/tables have
  a tenant_id column", which suits Citus distribution. **Skip now.** Keep the option open by
  carrying `organization_id` on hot telemetry tables (see #356).

## 2. RBAC at scale

| Platform | Unit of grant | Inherits down a tree | Custom roles | Per-object grants |
|---|---|---|---|---|
| NetBox | ObjectPermission (actions × types × JSON constraint) to users or groups | Via constraints such as `region__…` | Yes, free-form | Through constraints |
| Zabbix | Read, Read-write, Deny on a host group, to user groups | Optional push to nested groups | Roles narrow a type | No |
| Grafana OSS | Basic role per org; folder and dashboard permissions | Folders | Enterprise only | Dashboards only |
| OpenWISP | Permission groups plus `is_admin` per org | No | Django groups | No |
| LibreNMS | Global roles plus per-device or per-port grants | No | Yes | Yes (the scaling problem) |
| django-guardian | One row per user or group × permission × object | No | n/a | Yes |

- **NetBox constraints**
  ([permissions](https://github.com/netbox-community/netbox/blob/main/docs/administration/permissions.md)).
  Constraints are "a JSON object or list representing a Django query filter". Multiple
  permissions are merged with OR, and `$user` substitutes the requester. On write, NetBox saves
  inside a transaction, re-reads the object through the restricted queryset, and rolls back if
  it no longer matches. **Keep the idea, not the model.** `visibility.py` already compiles
  scope into `Q`. Free-form JSON constraints would let an admin write a filter that leaks across
  tenants, and that can't be tested. **Adopt the write check:** after a write, re-read the row
  through `visible_to()` and roll back if it fell outside the boundary. This catches a row moved
  into another tenant's building.
- **django-guardian**
  ([performance](https://github.com/django-guardian/django-guardian/blob/devel/docs/userguide/performance.md)).
  The default uses generic foreign keys, and the docs warn that for "thousands of users and their
  project/tickets, object level permission checks can be slow". The fix is a direct foreign-key
  table per model. At hundreds of thousands of units, any per-object scheme multiplies rows by
  users. **Skip for devices.** Keep it installed for a rare share of one object to one user.
- **Delegated administration for MSPs.** None of the OSS tools has a built-in "MSP manages these
  customers" relation. NetBox expresses it as constraints on `tenant__group`, Zabbix as
  user-group grants on a parent host group, and Grafana needs a membership per org. The
  lowest-maintenance version for micboard is a membership on the **provider** organization that
  applies to every customer whose `parent` is that provider, with the same role.

## 3. Identity

### SSO

- **django-auth-adfs** ([README](https://github.com/snok/django-auth-adfs),
  [settings](https://github.com/snok/django-auth-adfs/blob/main/docs/settings_ref.rst),
  BSD-2-Clause). "A Django authentication backend for Microsoft ADFS and Azure AD". It
  auto-creates users and mirrors groups (`MIRROR_GROUPS`), maps claims (`CLAIM_MAPPING`,
  `GROUP_TO_FLAG_MAPPING`), and authenticates DRF requests with an access token. Its config is one
  `AUTH_ADFS` dict, or one `SETTINGS_CLASS`, with exactly one `TENANT_ID` or `SERVER`. **Keep it**
  for enterprise installs with one Entra ID or ADFS tenant. It can't hold one IdP per MSP
  customer.
- **mozilla-django-oidc** ([README](https://github.com/mozilla/mozilla-django-oidc), MPL-2.0).
  One OIDC provider from settings. **Skip.** It has the same one-IdP limit, and it would add
  MPL-2.0, a file-level copyleft, to the dependency set.
- **django-allauth** (MIT)
  ([SAML](https://github.com/pennersr/django-allauth/blob/main/docs/socialaccount/providers/saml.rst),
  [OpenID Connect](https://github.com/pennersr/django-allauth/blob/main/docs/socialaccount/providers/openid_connect.rst),
  [MFA](https://github.com/pennersr/django-allauth/blob/main/docs/mfa/introduction.rst)). The SAML
  docs name the MSP case: "often you need to support multiple organizations, each having their own
  SAML based Identity Provider". Endpoints include the organization slug
  (`/accounts/saml/<organization_slug>/login/`). Each IdP's config is a `SocialApp`, editable in
  the admin, and the entity ID becomes the provider ID so that `(provider, uid)` stays unique
  across IdPs. The OIDC provider supports "multiple independent OpenID Connect providers", each
  with its own `server_url`. `allauth.mfa` adds TOTP, recovery codes, WebAuthn, and passkeys.
  **Adopt** as the multi-tenant login layer. Link each `SocialApp` to one `Organization`. On login,
  turn IdP group claims into memberships, the way Grafana's `org_mapping` does, so the IdP stays
  the source of truth.
- **djangosaml2** (Apache-2.0) and **python-social-auth** (BSD-3-Clause, which
  [NetBox uses for SSO](https://github.com/netbox-community/netbox/blob/main/docs/administration/authentication/overview.md)).
  Both are configured from settings. **Skip,** because allauth covers both protocols with DB-stored
  apps.
- **Identity brokers** (Keycloak Apache-2.0, authentik MIT core with an enterprise directory,
  Zitadel AGPL-3.0). Each is a full stateful service to patch and back up. **Skip as a
  dependency.** An MSP that already runs one points an allauth OIDC app at it.

### SCIM provisioning

- **django-scim2** ([README](https://github.com/15five/django-scim2), MIT) is "a provider-side
  implementation of the SCIM 2.0" (RFC 7643/7644). In Grafana, SCIM is Enterprise or Cloud only
  ([docs](https://github.com/grafana/grafana/blob/main/docs/sources/setup-grafana/configure-access/configure-scim-provisioning/_index.md)).
- **Verdict: defer.** JIT provisioning on SSO login plus group-claim mapping covers creation and
  role changes. SCIM adds *deprovisioning without a login*. Add it when a customer contract
  requires it. Scope each SCIM bearer token to one organization through the same service
  principal model as edge listeners.

### API tokens

- **django-rest-knox** ([auth](https://github.com/jazzband/django-rest-knox/blob/develop/docs/auth.md),
  [settings](https://github.com/jazzband/django-rest-knox/blob/develop/docs/settings.md), MIT).
  Tokens are stored hashed ("By default, Knox uses SHA-512 to hash tokens"). They support
  `TOKEN_TTL`, `TOKEN_LIMIT_PER_USER`, and `AUTO_REFRESH` with `AUTO_REFRESH_MAX_TTL`. There are no
  scopes.
- **NetBox v2 tokens** ([token model](https://github.com/netbox-community/netbox/blob/main/docs/models/users/token.md)).
  "stored only as a salted HMAC digest", with a plaintext key prefix for lookup. Fields include
  description, expiry, last used ("updated at most once per minute"), enabled, **write enabled**,
  and **allowed IPs**.
- **Verdict: adopt Knox and extend it.** A token always belongs to a user. Machines get a
  *service principal*: a user row flagged non-interactive, owned by one organization, with one
  role binding. Add a small companion model on Knox's `AuthToken` for description, last used
  (throttled), read-only, allowed CIDRs, and the principal kind.

### Audit logging

- **django-simple-history** ([README](https://github.com/django-commons/django-simple-history),
  BSD-3-Clause) keeps a full historical row per change, and the admin already uses it.
- **django-auditlog** ([README](https://github.com/jazzband/django-auditlog), MIT) "saves a
  summary of the changes in JSON format" and records the actor.
- **Verdict: adapt.** Don't add a second change-tracking library. Keep simple-history for
  model diffs. Add one append-only `AuditEvent` table (organization, actor user or principal,
  principal kind, action, object reference, source IP, request ID, JSON details) for
  security events that aren't row changes: logins, SSO failures, token creation and use,
  role grants, listener enrolment and revocation, and exports. Fold `ConfigurationAuditLog`
  into it later. Tenant admins can read their own organization's events.

## 4. Fleet operations for edge listeners

### Zabbix proxy

- **Source:** [proxies](https://www.zabbix.com/documentation/current/en/manual/distributed_monitoring/proxies),
  [proxy load balancing and HA](https://www.zabbix.com/documentation/current/en/manual/distributed_monitoring/proxies/ha),
  [version compatibility](https://www.zabbix.com/documentation/current/en/manual/appendix/compatibility).
  AGPL-3.0.
- **Pattern:** an active proxy "will connect to the Zabbix server and request configuration data".
  It "requires only one TCP connection" and stores "all data collected by the proxy … locally
  before transmitting" (`ProxyLocalBuffer`, `ProxyOfflineBuffer`). It "does not calculate
  triggers, process events or send alerts". Proxy groups move hosts off a proxy as soon as it is
  offline for longer than the failover delay (default 1 minute). A proxy that matches the server
  major version is **current**. An **outdated** proxy can still collect data but "cannot receive
  configuration updates". An **unsupported** proxy gets nothing. Connections use PSK or
  certificates.
- **Mapping:** a proxy is an edge listener, a proxy group is the set of listeners on one campus,
  and a host is a chassis or Device Manager.
- **Verdict: adopt the pattern.** Outbound pull of a versioned config. No alerting at the edge.
  Store-and-forward. A three-state version window. Optional failover between listeners on the same
  campus by reassigning devices.

### Mender device authentication

- **Source:** [device authentication](https://docs.mender.io/overview/device-authentication),
  [mender](https://github.com/mendersoftware/mender), and
  [mender-server](https://github.com/mendersoftware/mender-server). Apache-2.0. RBAC, dynamic
  groups, and delta updates are commercial.
- **Pattern:** the device signs an auth request with its private key and sends its identity and
  public key. Each authentication set is **pending**, **accepted**, **rejected**, or
  **preauthorized**, and "only one set per Device can be accepted". Preauthorization lets the
  first request succeed, "suits production batches". Tokens are JWTs that expire after a week by
  default and renew automatically.
- **Verdict: adopt the states, skip the OTA server.** Listener enrolment uses the same four
  states. A single-use enrolment token counts as preauthorization. Without one, a request lands
  in `pending` for a tenant admin to accept.

### Balena

- **Source:** [configuration](https://docs.balena.io/learn/manage/configuration/),
  [supervisor API](https://docs.balena.io/reference/supervisor/supervisor-api/),
  [balena-supervisor](https://github.com/balena-os/balena-supervisor) (Apache-2.0),
  [open-balena](https://github.com/balena-io/open-balena) (AGPL-3.0).
- **Pattern:** fleet variables apply to every device, and "device level configuration redefines
  (or overrides) fleet wide configuration". The supervisor reports `applying` or `applied` and
  honours update locks.
- **Verdict: adopt layered config, skip the platform.** Resolve a config document from
  deployment defaults, then organization, campus, and listener. Version it with a hash, and let
  the listener report which revision it applied. An update lock maps to "don't restart the
  listener while a show is live", which is a listener-side flag that the server respects.

### Fleet and osquery (orbit)

- **Source:** [orbit README](https://github.com/fleetdm/fleet/blob/main/orbit/README.md),
  [agent configuration](https://fleetdm.com/docs/configuration/agent-configuration). Core is MIT,
  and `ee/` is under a commercial license.
- **Pattern:** hosts enroll with an enroll secret per team. Revoking a secret stops config updates
  for hosts that enrolled with it. Agent options apply "without a fleetd restart" on the next
  config poll ("up to 30 seconds"). Orbit updates from a TUF repository with release channels,
  and self-managed update servers are a Premium feature.
- **Verdict: adapt.** Enroll secrets scoped to an organization or campus, revocable, and listed in
  the admin. Skip TUF: signed container images and a pinned tag give the same guarantee.

### Tailscale and headscale

- **Source:** [auth keys](https://tailscale.com/kb/1085/auth-keys),
  [tailscale](https://github.com/tailscale/tailscale) (BSD-3-Clause),
  [headscale](https://github.com/juanfont/headscale) (BSD-3-Clause).
- **Pattern:** keys are one-off or reusable, ephemeral, pre-approved, or tagged. A tagged device
  "assumes the identity of the auth key's tags" rather than the creator's, and key expiry is off
  for tagged devices. Auth keys last 1 to 90 days.
- **Verdict: optional.** Copy the semantics: a listener's identity is its campus scope, not the
  admin who enrolled it, and enrolment tokens are single-use and expire. Document a tailnet as an
  optional remote-support path. Never require it for telemetry.

### OpenWISP controller

- **Source:** [auto-registration](https://openwisp.io/docs/stable/openwrt-config-agent/user/automatic-registration.html),
  [config status](https://openwisp.io/docs/stable/controller/user/device-config-status.html),
  [settings](https://openwisp.io/docs/stable/controller/user/settings.html). GPL-3.0.
- **Pattern:** an agent with no `uuid` and `key` registers "only if `shared_secret` is correctly
  set" and stores the returned credentials. A consistent key derived from the MAC and the secret
  lets a reflashed device be recognized. Config status is `modified`, `applied`, `error`,
  `deactivating`, or `deactivated`.
- **Verdict: adopt the config status vocabulary.** Skip MAC-derived keys: a listener in a
  container should keep its key on a volume, and re-enrolment should be explicit.

### hawkBit

- **Source:** [hawkbit](https://github.com/eclipse-hawkbit/hawkbit). EPL-2.0, Java, with
  optional RabbitMQ for its DMF API. **Skip.** It's a second JVM service for an OTA problem
  micboard doesn't have.

## 5. HA, DR, and multi-region

- **Patroni** ([README](https://github.com/patroni/patroni), MIT) is "a template for PostgreSQL HA"
  using etcd, Consul, ZooKeeper, or Kubernetes for consensus. **CloudNativePG**
  ([README](https://github.com/cloudnative-pg/cloudnative-pg), Apache-2.0) is a Kubernetes
  operator with failover, rolling updates, and `Backup`, `ScheduledBackup`, and `Pooler`
  resources. Managed Postgres puts both concerns on the provider.
  **Verdict:** micboard ships no HA code. The deployment guide recommends managed Postgres and
  names CloudNativePG for Kubernetes self-hosting. Patroni needs a DCS cluster, so it is the most
  operational work for one maintainer.
- **Backups:** **pgBackRest** ([repo](https://github.com/pgbackrest/pgbackrest), MIT) and
  **WAL-G** ([repo](https://github.com/wal-g/wal-g), Apache-2.0) both give base backups plus WAL
  archiving for point-in-time recovery. **Verdict:** document both. Add a restore drill to the
  release checklist. micboard-specific DR is short: Postgres plus the media volume (organization
  logos). Huey and Channels keep state in Redis, which can be rebuilt.
- **Edge listeners in DR:** because listeners buffer and pull config, as Zabbix proxies do, a
  central failover loses no telemetry inside the buffer window. Size the buffer to the RTO.
- **Data residency per tenant:** Django can route models to different databases with routers
  ([multiple databases](https://docs.djangoproject.com/en/5.2/topics/db/multi-db/)), but routing
  *one tenant's rows* to another database breaks cross-tenant queries, migrations, and the
  provider view. **Verdict: cells.** Run one deployment per jurisdiction, each with its own
  database, Redis, and object storage. An MSP spanning jurisdictions has one provider
  organization per cell. A tenant is pinned to one cell at creation. Add Postgres row-level
  security ([docs](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)) later as
  defense in depth on the hottest tables only, after `organization_id` is denormalized there.

## 6. Product surface

- **Public REST API:** DRF, drf-spectacular, and Knox are already in the standard stack (ADR-007).
  Every viewset uses `visible_to()`. Service principals use the same API with their scope.
- **Webhooks:** NetBox sends webhooks from event rules, and its `secret` adds "a `X-Hook-Signature`
  header … HMAC (SHA-512) hex digest of the request body"
  ([webhook model](https://github.com/netbox-community/netbox/blob/main/docs/models/extras/webhook.md)).
  It also offers a `header_safe` filter against header injection. The
  [Standard Webhooks spec](https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md)
  (Apache-2.0) fixes `webhook-id` (an idempotency key that stays the same across retries),
  `webhook-timestamp`, and `webhook-signature` (HMAC-SHA256, with several space-separated
  signatures during key rotation). **Verdict: adopt the spec, not a server.** A
  `WebhookEndpoint` per organization with event types, a write-only secret (per #343, only
  `has_secret` is returned), and a `WebhookDelivery` row per attempt sent by a Huey task with
  backoff. Payloads are fixed DTOs, not user templates: NetBox's Jinja bodies are a code-execution
  surface that its own docs flag. Svix (MIT) is skipped as an extra service.
- **Quota and entitlement per tenant:** `Organization.max_devices` and `subscription_tier` exist.
  **Verdict: adapt.** Move tier limits into an `EntitlementService` that reads a code-defined
  table per tier, with nullable overrides on the organization. Check limits at creation time
  (chassis, units, campuses, edge listeners, API tokens, webhook endpoints). Over-limit blocks
  *new* resources and never stops monitoring existing ones. Billing stays outside micboard.
- **White-labelling:** django-unfold's `SITE_LOGO`, `SITE_ICON`, and `SITE_FAVICONS` take
  callables with `request`, while `COLORS` is static
  ([settings](https://unfoldadmin.com/docs/configuration/settings/)). **Verdict: adopt.** Resolve
  branding from the provider organization of the request's Django Site, falling back to the
  customer organization's `logo` and `primary_color`. Apply colour through a CSS variable in the
  operator UI rather than unfold's static palette. Each MSP portal is a Django Site with its
  own hostname.

## Recommended tenancy and location hierarchy

```text
Deployment cell  (one install per jurisdiction: Postgres, Redis, object storage)
│
├── Django Site  (portal hostname and branding; SITE_ID per process)      [existing, optional]
│
└── Provider organization  (Organization, kind=provider): the MSP          [new: kind, parent]
    │   provider memberships apply to every child customer
    │
    └── Customer organization  (Organization, kind=customer): the tenant   [existing]
        │   SSO app (allauth SocialApp), webhooks, entitlements, service principals
        │
        ├── Region  (optional, nested, ltree path; grouping and delegation) [new]
        │   │
        │   └── Campus  (physical site: address, timezone)                  [existing, + region]
        │       │
        │       ├── Edge Listener  (1..n per campus; enrolled service principal)  [new]
        │       │     owns device sessions for the chassis assigned to it
        │       │
        │       └── Building                                                [existing, real FKs]
        │           └── Room                                                [existing]
        │               └── Location  (placement in a building, optional room)  [existing]
        │                   └── Chassis · RF Distribution Unit · Charger
        │                         └── RF Channel → Wireless Unit
        │
        └── Monitoring groups  (cross-cutting reach for viewers and operators)  [existing]
```

- **Site** means the Django Site everywhere: a portal and deployment partition chosen per
  process. The physical site is **Campus**. Record this in `CONTEXT.md`, because "site" means
  something else in NetBox and in plain speech.
- **Edge Listener** attaches to a **Campus**, because listeners are deployed per physical site and
  discovery doesn't cross routers (#354). Each chassis or Device Manager connection records which
  listener owns its session. A null value means the central realtime process owns it.
- **Single-tenant and enterprise installs** get one default organization with no provider and
  one default campus. The tree is the same, with fewer rows.

## Recommended RBAC model

- **Roles are fixed in code:** `viewer`, `operator`, `admin`, and `owner` (existing), plus two
  principal kinds that aren't people: `listener` (write telemetry and session state for its campus
  only, with no UI) and `integration` (API read, plus optional write per token).
- **A role binding is a principal, a role, and a scope.** The scope is one of organization,
  region, or campus. `OrganizationMembership` becomes this binding. Its existing `campus` column
  shows scopes narrower than an organization already exist.
- **Inheritance goes down only:** a binding on a provider organization applies to its customers,
  a binding on a region applies to the campuses in its subtree, and a binding on a campus applies
  to its buildings and devices. There is no Deny. The most permissive binding wins, as in Zabbix
  without Deny.
- **Monitoring reach still narrows viewers and operators** inside a scope, unchanged from
  `visibility.py`. Admins and owners see their whole scope.
- **Groups:** bindings can target a Django `Group` mirrored from IdP claims, so the IdP manages
  membership, the way Zabbix grants go only to user groups and Grafana uses `org_mapping`.
  Direct user bindings stay allowed for small tenants.
- **Owner rule (OpenWISP):** an organization has exactly one owner, and only the owner or a
  superuser can transfer it.
- **Provider staff:** a provider `viewer` gets read access to every customer, which replaces the
  global `allow_cross_org_view` switch for MSP staff. A provider `admin` can manage customer
  memberships. A customer can't see the provider's other customers.
- **Writes:** after a mutation, re-read the row through `visible_to()` inside the transaction and
  roll back if it fell outside the scope (NetBox).
- **Per-object exceptions:** django-guardian, with direct foreign keys, only for sharing one object
  with one user. Never for devices.

## Identity and fleet-ops architecture

```text
            Customer IdP (Entra ID / ADFS / Okta / Keycloak / ...)
                 │  OIDC or SAML, one SocialApp per organization
                 ▼
 Browser ──► allauth login ──► JIT user + group claims ──► role bindings (scope)
                 │                                         │
                 │  local accounts: allauth.mfa (TOTP, passkeys)
                 ▼                                         ▼
           Django session ───────────────► visibility.py ◄── Knox token (service principal)
                                                │                 ▲            ▲
                                             AuditEvent           │            │
                                                             integrations   Edge Listener
                                                                               │
 Edge listener lifecycle:                                                      │
   1. Admin creates an EnrolmentToken (campus scope, single use, expires ≤ 7 days)
   2. Listener POSTs token + public key + version  ──► EdgeListener(state=preauthorized→accepted)
      (no token → state=pending, tenant admin accepts or rejects)
   3. Server issues a Knox token for the listener's service principal (TTL + auto-refresh)
   4. Heartbeat every N s: version, uptime, buffer depth, config revision, device counts
   5. GET config?since=<revision>  → layered config (org → campus → listener), hash-versioned
      listener reports applied | error  (OpenWISP vocabulary)
   6. desired_version on the server; listener reports current; state current | outdated |
      unsupported (Zabbix window); host pulls the pinned image tag
   7. Revoke: state=rejected, Knox tokens deleted, sessions reassigned to a peer listener
```

- **Django-auth-adfs** stays as the single-IdP option for enterprise installs that already use it.
  With allauth, the same Entra ID tenant is just one OIDC `SocialApp`.
- **Health** is "last heartbeat within a timeout", logged once per transition, using the same
  availability rule as #343. Listener offline becomes an alert in the owning organization.
- **No remote shell, no OTA.** Upgrades are a pinned container tag that the host's orchestrator
  pulls. micboard only records desired and actual versions and refuses config to unsupported
  listeners.

## Schema migrations needed

Each one needs approval under the migration rules in `AGENTS.md`, and should be applied with
django-safemigrate. They are listed in dependency order.

1. **Organization hierarchy:** add `Organization.kind` (`provider`, `customer`; default `customer`)
   and a nullable `Organization.parent` foreign key to self, with a check that a parent is a
   provider and a provider has no parent.
2. **Always-on tenancy:** a data migration creates a default organization and campus when none
   exist, and assigns orphan buildings to them. Then fold `micboard.multitenancy` into core.
   Convert `Building.organization_id` and `campus_id` into real foreign keys (`PROTECT`), and make
   `campus` required. This step can later remove the single and site branches in
   `visibility.py`.
3. **Region:** a new `Region` model (organization foreign key, parent, name, slug, `ltree` path or
   materialized path, unique name per parent) and a nullable `Campus.region` foreign key.
4. **Role bindings:** generalize `OrganizationMembership` into a binding with a principal (user or
   group), a role, and a scope (organization, region, or campus, one non-null). Replace
   `unique_together` with `UniqueConstraint`s (#325). Add a partial unique constraint for one owner
   per organization.
5. **Service principals:** a `ServicePrincipal` (one-to-one to user, organization, kind
   `listener`/`integration`/`scim`, `is_interactive=False`) and an `ApiTokenMeta` alongside Knox
   `AuthToken` (description, last used, read only, allowed CIDRs).
6. **Edge listeners:** `EdgeListener` (campus, principal, name, state
   `pending`/`preauthorized`/`accepted`/`rejected`, public key fingerprint, reported version,
   desired version, version state, last heartbeat, config revision applied, config status) and
   `EnrolmentToken` (scope, hashed token, expiry, used at, created by).
7. **Session ownership:** a nullable `edge_listener` foreign key on chassis and on the Device
   Manager connection model from ADR-015.
8. **Layered config:** `ListenerConfigOverride` rows at organization, campus, or listener scope, as
   JSON validated by a Pydantic DTO.
9. **SSO linkage:** `OrganizationIdentityProvider` linking an allauth `SocialApp` to an
   organization, with a group-claim to role mapping. allauth's own migrations come with the
   package.
10. **Audit:** an append-only `AuditEvent` with an index on `(organization, created_at)`. Later,
    fold `ConfigurationAuditLog` into it.
11. **Webhooks:** `WebhookEndpoint` (organization, URL, event types, encrypted secret, enabled) and
    `WebhookDelivery` (endpoint, `webhook-id`, attempt, status, next attempt time).
12. **Entitlements:** nullable override columns on `Organization` (`max_campuses`,
    `max_edge_listeners`, `max_api_tokens`, `max_webhook_endpoints`), with tier defaults in code.
13. **Branding:** nullable `Organization.portal_site` (or reuse `site`) and `favicon`. `logo` and
    `primary_color` already exist.
14. **Deferred:** `organization_id` denormalized onto hot telemetry tables (with #356), Postgres
    row-level security policies, and SCIM tables from django-scim2.

## Licensing

Only patterns are borrowed and no code is copied. The new dependencies proposed are django-allauth
(MIT) and, deferred, django-scim2 (MIT). Both are compatible with AGPL-3.0-or-later. Zabbix,
Grafana, and open-balena are AGPL-3.0. LibreNMS and OpenWISP controller are GPL-3.0. NetBox,
Mender, CloudNativePG, and Standard Webhooks are Apache-2.0. hawkBit is EPL-2.0, and it is
skipped. mozilla-django-oidc is MPL-2.0, and it is skipped. osquery is Apache-2.0 OR
GPL-2.0-only, and only its pattern is mentioned.
