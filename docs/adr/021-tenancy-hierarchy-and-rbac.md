---
title: "ADR-021: Tenancy Hierarchy, Cells, and Role Bindings"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

MSPs serve many customers across regions and jurisdictions. micboard had three deployment
modes (single, site, MSP) with branching visibility logic. Decided in [#368](https://github.com/justprosound/django-micboard/issues/368) and
[#369](https://github.com/justprosound/django-micboard/issues/369), from the tenancy research ([#357](https://github.com/justprosound/django-micboard/issues/357)).

## Decision

1. The hierarchy: **Cell** (one deployment per jurisdiction) → **Portal** (Django Site) →
   provider organization → customer organization → optional nested **Region** → **Campus** →
   Building → Room → Location → devices.
2. **Tenancy is always on.** Single-site becomes one default organization and campus, which
   removes the mode branches.
3. RBAC: fixed roles (`viewer`, `operator`, `admin`, `owner`, plus `listener` and `integration`
   principals) bound with a scope (organization, region, or campus). Inheritance goes down only,
   with no deny rules. Monitoring reach still narrows viewers and operators. Bindings may target
   groups from identity-provider claims. Each organization has one owner. A provider viewer
   replaces `allow_cross_org_view`.
4. After a write, the row is re-read through `visible_to()` in the same transaction.
5. Residency is enforced by cells, not by routing one tenant to its own database.

## Consequences

- `Organization` gains `kind` and `parent`, and memberships become scoped bindings, both by
  expand and contract.
- django-guardian is used only for sharing one object with one user.

## Alternatives considered

- **Per-tenant databases or schemas:** rejected. They break provider views and cross-tenant
  migrations.
- **Deny rules:** rejected, because they're hard to reason about and to audit.
