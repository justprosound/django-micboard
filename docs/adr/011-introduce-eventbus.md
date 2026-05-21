# ADR-011: Introduce EventBus for Signal-Based Communication

**Status:** Proposed
**Date:** 2026-05-21
**Deciders:** (to be assigned)

## Context

Events currently flow through three parallel mechanisms with no central coordination point:

| Mechanism | Seam | Location | Used For |
|-----------|------|----------|----------|
| Django model signals | `post_save`, `pre_delete`, etc. | Scattered across models and receivers | Side-effects after model save (discovery triggers, status updates) |
| Custom signal emitter | `services/notification/signal_emitter.py` (182L) | Single file with 6 methods | Centralized signal emission with typed payloads |
| WebSocket broadcasting | `services/notification/broadcast_service.py` (187L) | Single file with 7 methods | Real-time UI updates via WebSocket |

The problem is not that events exist — it's that there is no single seam where "something happened" is declared. A developer tracing what happens when a chassis is saved must check:
1. The model's `save()` override (side effects)
2. django-lifecycle hooks on the model (state transitions)
3. `post_save` signal receivers (discovery, sync triggers)
4. `signal_emitter.py` calls in views/tasks (explicit emission)
5. Direct `broadcast_service.py` calls near the emission site

This makes it:
- **Impossible to test in isolation.** Testing a model `save()` tests the full cascade — side effects, signals, broadcasts — unless you mock at the Django signal level (string-based names, no type safety).
- **Hard to audit.** There is no single import that reveals "what events does this module produce?".
- **Impossible to add cross-cutting concerns** (logging, metrics, dead-letter) without touching every emission site.

## Decision

1. **Introduce an `EventBus` seam** — a single class with two methods:

   ```python
   class EventBus:
       def publish(self, event_type: str, payload: dict, source: str = "") -> None: ...
       def subscribe(self, handler: Callable, event_type: str) -> None: ...
   ```

   The `EventBus` itself is ~40 lines. It routes `publish` calls to subscribed handlers synchronously (in-process). It does not replace Celery/django-q2 for async distribution — it replaces ad-hoc signal wiring.

2. **All three existing mechanisms become adapters behind this seam:**
   - Django model signals → add a `dispatch()` hook at the signal connection point that calls `EventBus.publish()`. The model signal is no longer wired directly to service logic — it publishes an event.
   - `signal_emitter.py` → becomes an adapter module that calls `EventBus.publish()` and is then deprecated in favour of direct `event_bus.publish()` calls.
   - WebSocket broadcasting → an `EventBus` subscriber that calls `broadcast_service.py`.

3. **The EventBus is injectable.** Each service or view that emits events receives an `EventBus` instance (via constructor injection or a module-level singleton that can be replaced in tests). Tests use a `FakeEventBus` that records published events for assertion.

4. **Event types are strings** (namespaced, e.g., `"chassis:created"`, `"chassis:status_changed"`, `"discovery:completed"`). This keeps the seam lightweight — no new base classes to import.

5. **No replacement for django-q2.** Background task distribution remains in tasks. The EventBus is for in-process notification only. If a handler needs async execution, it publishes a task to django-q2.

## Example Test Pattern

```python
def test_chassis_creation_publishes_event():
    bus = FakeEventBus()
    service = HardwareLifecycleService(event_bus=bus)
    service.save_chassis(...)
    assert ("chassis:created", payload) in bus.published_events
```

## Consequences

- **Positive:** One import answers "what events flow through this system?" — `EventBus.publish()` calls. Testing becomes straightforward: assert against `FakeEventBus.published_events`. Adding cross-cutting concerns (event logging, metrics, dead-letter queue) requires touching only the EventBus class, not every emission site.
- **Negative:** ~30-40 emission sites need to change from direct signal/signal_emitter/broadcast calls to `EventBus.publish()`. Django signal receivers and `signal_emitter.py` become redundant and must be removed. Existing model signal handlers need to be audited to decide which become EventBus subscribers vs. direct service calls.
- **Migration:** Four-phase approach:
   1. Implement `EventBus` and `FakeEventBus` (~80 lines total).
   2. Wire it into the application entry point (AppConfig.ready() or middleware).
   3. Migrate emission sites bottom-up: start with `signal_emitter.py`, then broadcast calls, then model signal handlers. Each migration replaces the old mechanism with `EventBus.publish()` and adds a subscriber where needed.
   4. Remove Django signal connections and `signal_emitter.py` after all emissions migrated.

## Compliance

- New code must use `EventBus.publish()` for event notification — no new Django signal connections or direct broadcast calls.
- CI will flag any new `@receiver(post_save)` or `@receiver(pre_delete)` decorators (exception: user-registration signals).
