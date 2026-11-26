---
title: "ADR-003: Admin code is organized by domain"
description: "Why the Django admin is one module per domain and holds no business logic."
type: explanation
audience: developer
---

## Context

A single 2,400-line admin dashboard module mixed chassis management, unit CRUD, chargers, manufacturer configuration, discovery approval, settings diffing and monitoring.

## Decision

- Each functional area has its own module under `micboard/admin/`, registered against one domain: `receivers.py` (chassis), `channels.py` (units and RF channels), `chargers.py`, `configuration.py`, `discovery_admin.py`, `monitoring.py`, `settings.py` and others. Each routes only to its domain's models.
- Admin classes are thin presentation adapters. Authorization-sensitive sequences (for example bulk chassis deletion) live in a service that checks authorization first, as `services/hardware/chassis_bulk_delete_service.py` does.
- Views that were never registered or routed are deleted, not retained, because unscoped global data views are a latent security hazard.

## Consequences

Admin modules are independently navigable and testable, and merge conflicts are rarer. Splitting by domain does not by itself make a module thin: logic that creeps back in belongs in a service.
