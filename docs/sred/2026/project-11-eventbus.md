<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Introduce EventBus for Signal-Based Communication

## Project Description

Events currently flow through two parallel mechanisms with no central coordination point. The unused custom signal-emitter facade was removed after it duplicated direct broadcasts:

| Mechanism | Seam | Location | Used For |
|-----------|------|----------|----------|
| Django model signals | `post_save`, `pre_delete`, etc. | Scattered across models and receivers | Side-effects after model save (discovery triggers, status updates) |
| WebSocket broadcasting | `services/notification/broadcast_service.py` (187L) | Single file with 7 methods | Real-time UI updates via WebSocket |

The problem is not that events exist — it's that there is no single seam where "something happened" is declared. A developer tracing what happens when a chassis is saved must check: (1) the model's `save()` override, (2) django-lifecycle hooks, (3) `post_save` signal receivers, (4) direct `broadcast_service.py` calls. This makes testing in isolation impossible (full cascade unless you mock at Django signal level — string-based names, no type safety), auditing hard (no single import reveals "what events does this module produce?"), and cross-cutting concerns (logging, metrics, dead-letter) impossible without touching every emission site.

## Project Goals

Introduce an `EventBus` seam — a single class with two methods: `publish(event_type: str, payload: dict, source: str = "")` and `subscribe(handler: Callable, event_type: str)`. The EventBus routes `publish` calls to subscribed handlers synchronously (in-process). It does not replace native Huey for async distribution — it replaces ad-hoc signal wiring. Both existing mechanisms become adapters behind this seam: Django model signals add a `dispatch()` hook that calls `EventBus.publish()`; WebSocket broadcasting becomes an `EventBus` subscriber calling `broadcast_service.py`. The EventBus is injectable — each service/view receives an instance (constructor injection or module-level singleton replaceable in tests). Tests use `FakeEventBus` recording published events for assertion. Event types are strings (namespaced, e.g., `"chassis:created"`, `"chassis:status_changed"`, `"discovery:completed"`). No new base classes to import.

## Technical Uncertainties

### Uncertainty #1: Migrating Existing Signal Handlers Without Breaking Side-Effect Ordering

**Description:** Current `post_save` handlers run in registration order and some depend on prior handlers' DB mutations. Moving to `EventBus.publish()` in signal handlers preserves order but introduces indirection. The uncertainty: can we guarantee ordering semantics match current behavior when handlers become EventBus subscribers?

**Experiments (Planned):**
- Phase 1: Implement `EventBus` + `FakeEventBus` (~80 lines)
- Phase 2: Wire into AppConfig.ready() as singleton
- Phase 3: Migrate broadcast calls first (single file, 7 methods) — replace `broadcast_service.chassis_updated()` with `event_bus.publish("chassis:updated", payload)`
- Phase 4: Migrate model signal handlers — each `@receiver(post_save)` becomes a subscriber; signal still fires but only calls `EventBus.publish()`
- Phase 5: Remove redundant Django signal connections after all emissions migrate

**Results / Learnings / Success:**
- (To be determined during implementation)

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-011 Introduce EventBus for Signal-Based Communication](../../adr/011-introduce-eventbus.md)

### Uncertainty #2: Testing Event Flows Without Mocking Django Signals

**Description:** Current tests that verify side-effects must either: (a) run full cascade (slow, brittle), or (b) mock `@receiver` decorators (string-based, no type safety). The uncertainty: does `FakeEventBus` provide a clean enough seam for unit testing service logic in isolation?

**Experiments (Planned):**
- `FakeEventBus` records `published_events: list[tuple[str, dict, str]]`
- Service tests: `bus = FakeEventBus(); service = MyService(event_bus=bus); service.do_thing(); assert ("expected:event", expected_payload) in bus.published_events`
- Cross-cutting concern test: wrap `EventBus.publish` with logging/metrics in one place; verify all events captured

**Results / Learnings / Success:**
- (To be determined during implementation)

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-011 Introduce EventBus for Signal-Based Communication](../../adr/011-introduce-eventbus.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / ADR | ~15% | ADR-011, EventBus design, migration plan |
| (engineer) | Implementation / Migration | ~35% | EventBus, broadcast adapter, signal migration |
| (engineer) | Testing / FakeEventBus | ~25% | Test patterns, cross-cutting concern integration |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-011 Introduce EventBus for Signal-Based Communication](../../adr/011-introduce-eventbus.md)

**PRs:**
- (EventBus core + FakeEventBus PR)
- (broadcast adapter PR)
- (signal handler migration PRs per domain)
- (CI enforcement PR: flag new `@receiver` decorators)