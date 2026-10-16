---
title: "ADR-024: Public Contract Versioning and Releases"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

Enterprises build on micboard's API, webhooks, and edge protocol, while the project forbids
internal backward-compatibility shims. Decided in [#385](https://github.com/justprosound/django-micboard/issues/385).

## Decision

1. Public contracts are versioned: the REST API (`/api/v1/`), webhook event schemas (Standard
   Webhooks), the edge envelope schema, and documented plugin traits.
2. A breaking change ships as a new version beside the old one for at least 12 months,
   announced with `Deprecation` and `Sunset` headers. The versioned surface isn't a shim.
3. Edges are supported N−1 minor versions behind.
4. The first CalVer release of each quarter is an LTS line with 12 months of security fixes.
5. CI diffs the contract schemas against the previous release, and a breaking diff without a
   version bump fails.

## Consequences

- Internal code stays shim-free. Only the published surfaces carry versions.

## Alternatives considered

- **SemVer with long-lived majors:** rejected, because CalVer and the release automation are
  already in place.
