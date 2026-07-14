# ADR-011: Introduce EventBus for Signal-Based Communication

**Status:** Proposed
**Date:** 2026-05-21
**Deciders:** (to be assigned)

## Context

Events currently flow through two parallel mechanisms with no central coordination point. The
unused custom signal-emitter facade was removed after it duplicated direct broadcasts:

| Mechanism | Seam | Location | Used For |
|-----------|------|----------|----------|
| Django model signals | `post_save`, `pre_delete`, etc. | Scattered across models and receivers | Side-effects after model save (discovery triggers, status updates) |
| WebSocket broadcasting | `services/notification/broadcast_service.py` (187L) | Single file with 7 methods | Real-time UI updates via WebSocket |

The problem is not that events exist — it's that there is no single seam where "something happened" is declared. A developer tracing what happens when a chassis is saved must check:
1. The model's `save()` override (side effects)
2. django-lifecycle hooks on the model (state transitions)
3. `post_save` signal receivers (discovery, sync triggers)
4. Direct `broadcast_service.py` calls near the emission site

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

   The `EventBus` itself is ~40 lines. It routes `publish` calls to subscribed handlers synchronously (in-process). It does not replace native Huey for async distribution — it replaces ad-hoc signal wiring.

2. **Both existing mechanisms become adapters behind this seam:**
   - Django model signals → add a `dispatch()` hook at the signal connection point that calls `EventBus.publish()`. The model signal is no longer wired directly to service logic — it publishes an event.
   - WebSocket broadcasting → an `EventBus` subscriber that calls `broadcast_service.py`.

3. **The EventBus is injectable.** Each service or view that emits events receives an `EventBus` instance (via constructor injection or a module-level singleton that can be replaced in tests). Tests use a `FakeEventBus` that records published events for assertion.

4. **Event types are strings** (namespaced, e.g., `"chassis:created"`, `"chassis:status_changed"`, `"discovery:completed"`). This keeps the seam lightweight — no new base classes to import.

5. **No replacement for native Huey.** Background task distribution remains in tasks. The EventBus is for in-process notification only. If a handler needs async execution, it schedules a Huey task.

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
- **Negative:** Emission sites need to change from direct signal or broadcast calls to
  `EventBus.publish()`. Existing model signal handlers need to be audited to decide which become
  EventBus subscribers versus direct service calls.
- **Migration:** Four-phase approach:
   1. Implement `EventBus` and `FakeEventBus` (~80 lines total).
   2. Wire it into the application entry point (AppConfig.ready() or middleware).
   3. Migrate broadcast calls and then model signal handlers. Each migration replaces the old
      mechanism with `EventBus.publish()` and adds a subscriber where needed.
   4. Remove redundant Django signal connections after all emissions migrate.

## Compliance

- New code must use `EventBus.publish()` for event notification — no new Django signal connections or direct broadcast calls.
- CI will flag any new `@receiver(post_save)` or `@receiver(pre_delete)` decorators (exception: user-registration signals).
