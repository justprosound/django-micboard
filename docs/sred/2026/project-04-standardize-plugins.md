# SRED Project Summary — 2026 Standardize Manufacturer Plugins

<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

## Project Description

Manufacturer integrations (Shure, Sennheiser) used a common directory shape but divergent protocols: Shure uses REST + WebSocket; Sennheiser SSCv2 uses REST + HTTP Basic-authenticated SSE with `Content-Location` configured over a separate connection. Shared HTTPS validation, bounded response handling, retries, rate limits, circuit breaking, health tracking, plugin lookup, and exception hierarchy existed in `micboard/services/common/base/` and `micboard/exceptions.py`. A broad inheritance tree for discovery/transformers would make protocol differences implicit with only two consumers.

## Project Goals

Compose plugins around shared transport/resilience contracts without forcing inheritance on protocol-specific code. Keep discovery, device endpoints, transforms, and streaming adapters manufacturer-local. Extract only proven pure helpers used by ≥2 live integrations. Keep `PluginRegistry` as construction boundary and manufacturer sync services as persistence/orchestration boundary. Contract-test each protocol against authoritative behavior.

## Technical Uncertainties

### Uncertainty #1: How Much Transport/Resilience to Share Without Forcing Protocol Assumptions

**Description:** The tension was between DRY (shared retry/circuit-breaker/rate-limit/health code) and protocol honesty (Shure WebSocket vs Sennheiser SSE have different connection lifecycles, auth flows, framing). A shared base client would inevitably leak one protocol's assumptions into the other.

**Experiments:**
- Spike: `BaseAPIClient` with abstract `connect()` / `subscribe()` — Shure implemented WebSocket; Sennheiser implemented SSE; but retry logic assumed HTTP semantics, broke SSE reconnection
- Spike: Composition over inheritance — `BaseHTTPClient` (transport) + `HealthTracker` (state) + `PollingOrchestrator` (coordination) as separate injectable components
- Adopted: Keep shared, verified transport and plugin contracts in `services/common/base/`; keep connection setup, auth, event framing, cleanup in each transport adapter. Share only subscription lifecycle (eligible inventory selection, transform, persistence, chassis projection, broadcast) in `services/realtime/subscription_lifecycle_service.py`

**Results / Learnings / Success:**
- Transport safety fixes (TLS verification, bounded responses) propagate to both integrations
- Protocol mechanics remain locally readable and independently testable
- New integrations get one stable transport/plugin seam without inheriting unrelated discovery/streaming assumptions
- Contract tests cover auth, bounded payloads, origin validation, connection lifecycle per protocol

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-004 Compose Manufacturer Plugins Around Shared Transport](../../adr/004-standardize-manufacturer-plugins.md)
- **Related:** [ADR-010 Split base_http_client.py](../../adr/010-split-base-http-client.md) (superseded by direct domain split)

### Uncertainty #2: Discovery Payload Normalization Without Common Transformer Base

**Description:** Shure and Sennheiser discovery responses have different field names, nesting, and type representations. A shared `BaseTransformer` would force both into a lowest-common-denominator schema, losing vendor-specific richness.

**Experiments:**
- Attempted: abstract `Transformer` class with `normalize()` — required 15+ abstract methods for vendor differences
- Adopted: manufacturer-local transformers in `integrations/<vendor>/transformers.py` — each produces canonical internal DTOs (`DiscoveredDeviceWrite`, `WirelessChassisWrite`, etc.) consumed by sync services. No shared base; sync services depend on DTO shape, not transformer hierarchy.

**Results / Learnings / Success:**
- Transformers are pure functions; trivially unit-testable with vendor fixture data
- Sync services unchanged when vendor adds fields — only transformer updates
- No inheritance coupling; adding Wisycom integration required zero changes to shared code

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-004 Compose Manufacturer Plugins Around Shared Transport](../../adr/004-standardize-manufacturer-plugins.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Contracts | ~25% | Transport contract design, ADR-004 |
| (engineer) | Implementation / Shure | ~35% | WebSocket adapter, Shure transformer, contract tests |
| (engineer) | Implementation / Sennheiser | ~35% | SSE adapter, Sennheiser transformer, contract tests |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-004 Compose Manufacturer Plugins Around Shared Transport](../../adr/004-standardize-manufacturer-plugins.md)
- [ADR-010 Split base_http_client.py](../../adr/010-split-base-http-client.md) (historical)

**PRs:**
- (transport contract PR)
- (Shure WebSocket adapter PR)
- (Sennheiser SSE adapter PR)
- (subscription lifecycle service PR)
- (contract test PRs per protocol)
