---
title: "ADR-020: Alerting Model"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

The existing `Alert` model mixes alert state with notification. Country scale needs
de-duplication, grouping, inhibition (an RF Distribution Unit fault should not page once per
channel), silences, escalation, and enterprise delivery. Decided in [#366](https://github.com/justprosound/django-micboard/issues/366) and refined
by [#374](https://github.com/justprosound/django-micboard/issues/374).

## Decision

1. One **Alert** per (rule, target), holding state, plus **Notification** rows for each
   delivery attempt. Acknowledging never clears an alert, and a severity rise re-arms it.
2. Rules are a condition plus a `for` duration, with hysteresis and a minimum hold time.
   Thresholds layer: tenant, then monitoring group, then Event. Each alert stores its firing
   reason as a typed record.
3. Alertmanager-style concepts, implemented in Django:
   - a routing tree to crews (monitoring groups or Event crews), never to performers;
   - grouping;
   - **inhibition:** an RF Distribution Unit fault, a suspected distribution fault, or an
     unreachable campus inhibits its downstream alerts;
   - silences and maintenance windows;
   - escalation.
4. Delivery: in-app, email, signed webhooks, and an external Alertmanager receiver for
   enterprise paging.
5. Edges evaluate their campus's rules locally during outages, and central de-duplicates on
   reconnect (ADR-017).

## Consequences

- The `Alert` split is a migration by expand and contract.
- Operator fault reports become another alert source with the same lifecycle.

## Alternatives considered

- **Running Prometheus Alertmanager as the core:** rejected, because rules need tenant, Event,
  and assignment context that lives in Django. It stays available as a delivery target.
