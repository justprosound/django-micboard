<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Consolidate Exception Hierarchy

## Project Description

django-micboard had two independent API exception roots: `micboard/exceptions.py` (structured domain hierarchy rooted at `MicboardError`) and `services/common/base/exceptions.py` (separate transport `APIError` and `APIRateLimitError`). Duplicate roots made catch boundaries ambiguous — circuit-open failures escaped manufacturer-specific catches even though ordinary transport failures did not. No single import revealed the full exception surface.

## Project Goals

Establish `micboard/exceptions.py` as the single authoritative hierarchy. `APIError`, `APIRateLimitError`, `APIAuthenticationError`, `APITimeoutError` inherit from `MicboardError` with structured codes and details. Manufacturer-specific exceptions stay in integration modules inheriting from root API types. `BaseHTTPClient` raises configured manufacturer exception for circuit-open failures with code `API_CIRCUIT_OPEN`. Optional bounded `httpx.Response` available on API exceptions; response bodies never read into public details implicitly. Delete `services/common/base/exceptions.py`; all call sites import canonical root directly. No re-export or compatibility module.

## Technical Uncertainties

### Uncertainty #1: Single Catch Root Without Losing Transport Metadata

**Description:** Transport exceptions (`APIRateLimitError`, `APITimeoutError`) needed to preserve rate-limit metadata (retry-after, limit, remaining) and optional `httpx.Response` for transport logic, while fitting into the domain hierarchy. The challenge: how to carry structured transport data without exposing vendor response text.

**Experiments:**
- Attempted: wrapper exception with `.original` attribute — broke `isinstance` checks in catch blocks
- Adopted: `APIError` subclasses carry `code`, `details` dict, and optional `response` (httpx.Response, never read implicitly); rate-limit metadata in `details["retry_after"]`, `details["limit"]`, `details["remaining"]`

**Results / Learnings / Success:**
- Single `except MicboardError` catches all domain + integration failures
- Rate-limit handlers access `exc.details["retry_after"]` without type narrowing
- Vendor response text never leaks into logs; only structured codes/details

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-009 Consolidate Exception Hierarchy](../../adr/009-consolidate-exception-hierarchy.md)
- **Code:** `micboard/exceptions.py`

### Uncertainty #2: Circuit-Open Failures Through Manufacturer Catches

**Description:** Circuit breaker open state previously raised a generic transport exception that didn't match manufacturer-specific catch blocks (e.g., `except ShureAPIError`). Needed `BaseHTTPClient` to raise the *manufacturer's* exception type with circuit-open code.

**Experiments:**
- Modified `BaseHTTPClient` to accept manufacturer exception class in constructor; on circuit open, instantiate that class with `code="API_CIRCUIT_OPEN"`, `details={"circuit": "open", "retry_after": ...}`

**Results / Learnings / Success:**
- Existing `except ShureAPIError` blocks catch circuit-open automatically
- No catch-site changes required; behavior preserved

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-009 Consolidate Exception Hierarchy](../../adr/009-consolidate-exception-hierarchy.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Hierarchy Design | ~20% | Exception tree, ADR-009 |
| (engineer) | Implementation / Migration | ~30% | BaseHTTPClient changes, call-site updates |
| (engineer) | Testing / Contract Tests | ~20% | Catch boundary tests, metadata preservation |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-009 Consolidate Exception Hierarchy](../../adr/009-consolidate-exception-hierarchy.md)

**PRs:**
- (hierarchy consolidation PR)
- (BaseHTTPClient circuit-open PR)
- (call-site migration PR)
