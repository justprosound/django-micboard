---
title: "ADR-009: One exception hierarchy"
description: "Why all micboard errors derive from MicboardError in a single module."
type: explanation
audience: developer
---

## Context

Two independent exception roots existed: the domain hierarchy in `micboard/exceptions.py` and a separate transport `APIError` family. Catch boundaries were ambiguous, and circuit-open failures escaped manufacturer-specific handlers.

## Decision

- `micboard/exceptions.py` is the single authoritative hierarchy, rooted at `MicboardError`. `APIError`, `APIRateLimitError`, `APIAuthenticationError` and `APITimeoutError` inherit from it and carry structured codes and details.
- Manufacturer exceptions stay inside their integration and inherit from the root API types.
- `BaseHTTPClient` raises the manufacturer's exception with code `API_CIRCUIT_OPEN` when its circuit is open.
- Service modules define no exception roots of their own. Operational failures that need a public identity are added to `micboard/exceptions.py`.
- Django authorization and validation errors, Pydantic validator errors and programmer errors stay native at their framework boundaries. Public service seams translate unexpected failures to fixed, secret-safe structured errors.
- Response bodies are never copied into public error details.

## Consequences

One catch root and one payload shape cover domain and integration failures. Exception strings use the structured `MicboardError` format. The hierarchy is listed in the [exceptions reference](../api/reference/exceptions.md).
