---
title: "ADR-007: A versioned, read-only REST API"
description: "Why the REST API is versioned by namespace and read-only."
type: explanation
audience: developer
---

## Context

All programmatic access used to mean reverse-engineering the admin views. Integrations need a documented contract that can change without breaking existing clients.

## Decision

- Django REST Framework serves the API from `micboard/api/v1/`, with serializers in `micboard/serializers/v1/`.
- Version 1 is read-only (`ReadOnlyModelViewSet`), authenticated, and scoped with `visible_to()`. This avoids write-side validation and conflict rules until they are needed.
- A breaking change gets a new namespace (`micboard/api/v2/`) beside v1. Changes inside a version stay backward compatible.
- The Django admin stays the primary UI. The API is for programmatic use.

## Consequences

Integrations get a stable surface and a tenant-safe default. The cost is another surface to maintain next to the admin forms. The routes are listed in [HTTP endpoints](../api/endpoints.md).
