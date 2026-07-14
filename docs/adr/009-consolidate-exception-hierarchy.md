# ADR-009: Consolidate Exception Hierarchy

**Status:** Implemented
**Date:** 2026-05-21
**Updated:** 2026-07-14
**Deciders:** Project team

## Context

django-micboard had two independent API exception roots:

| File | Content |
|---|---|
| `micboard/exceptions.py` | Structured domain hierarchy rooted at `MicboardError`. |
| `services/common/base/exceptions.py` | Separate transport `APIError` and `APIRateLimitError`. |

The duplicate roots made catch boundaries ambiguous. Circuit-open failures also escaped
manufacturer-specific catches even though ordinary transport failures did not.

## Decision

1. `micboard/exceptions.py` is the single authoritative hierarchy. `APIError`,
   `APIRateLimitError`, `APIAuthenticationError`, and `APITimeoutError` inherit from
   `MicboardError` and expose structured codes and details.
2. Manufacturer-specific exceptions stay in their integration modules and inherit from the root
   API types.
3. `BaseHTTPClient` raises its configured manufacturer exception for circuit-open failures with
   code `API_CIRCUIT_OPEN`.
4. An optional bounded `httpx.Response` remains available on API exceptions for transport logic;
   response bodies are never read into public details implicitly.
5. `services/common/base/exceptions.py` is deleted and all call sites import the canonical root
   directly. No re-export or compatibility module remains.

## Final Hierarchy

```text
Exception
  MicboardError
    APIError
      APIRateLimitError
      APIAuthenticationError
      APITimeoutError
      ShureAPIError
      SennheiserAPIError
    ManufacturerNotSupportedError
    HardwareNotFoundError
    HardwareValidationError
    LocationNotFoundError
    LocationAlreadyExistsError
    DiscoveryError
    ServiceError
```

## Consequences

- **Positive:** One catch root and one structured payload contract cover domain and integration
  failures.
- **Positive:** Rate-limit metadata and response objects remain available without exposing vendor
  response text.
- **Negative:** Transport exception strings now use the structured `MicboardError` format.

## Compliance

- No new exception modules outside `micboard/exceptions.py` or plugin-local exception files.
- Call sites import root exceptions directly; aliases and re-exports are forbidden.
