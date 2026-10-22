---
title: "ADR-022: Per-organization Single Sign-on"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

The standard stack's `django-auth-adfs` serves one identity provider per install. An MSP needs
one per customer, and local accounts need MFA. Decided in [#370](https://github.com/justprosound/django-micboard/issues/370).

## Decision

1. **django-allauth** (MIT) provides one OIDC or SAML app per organization, just-in-time users,
   and group-claim mapping to role bindings. Local accounts require MFA (TOTP and passkeys).
2. `django-auth-adfs` stays supported for single-IdP installs.
3. Knox tokens authenticate edges and integrations. DRF's order stays Knox first, then session.
4. An append-only `AuditEvent` table, partitioned by time, records security-relevant actions.
5. SCIM is deferred. Leavers are deactivated by an inactivity job.

## Consequences

- This deliberately extends the standard stack, because it can't express a multi-tenant
  identity setup with one IdP per customer.

## Alternatives considered

- **ADFS only:** rejected, because it can't do one IdP per customer.
- **An external IdP broker (Keycloak):** rejected as another service to operate.
