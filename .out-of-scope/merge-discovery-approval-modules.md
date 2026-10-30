# Merging the discovery approval modules

This project keeps discovery approval as five small modules under `micboard/services/sync/`
(`discovery_approval_service`, `_plan`, `_policy`, `_resolution` and `_inventory`) and does not
merge them into one or two files.

## Why this is out of scope

A merge was evaluated in #467 and rejected on evidence:

- **No size case.** Merging plan, policy and resolution gives about 440 to 460 lines, over the
  repo's ~400-line guideline, and merging all five gives about 1,000. The split was not made to
  satisfy that guideline in the first place: it came from bounding lock scope and deepening
  inventory planning (commit 9e84d6f, #98).
- **No defect signal.** The cluster has existed since July 2026 and none of its commits fixed a
  cluster-specific bug. The files change together in most commits, but only because the
  hardening and typing sweeps touched all of them.
- **Coupling is clean.** The imports form a strict DAG with no cycles. The batch policy's
  seven dicts are instance-local to one batch and order-independent. The one real ordering
  dependency (lock queue rows, then addresses, then inventory in primary-key order) lives in
  `DiscoveryApprovalService.approve()` and has a test for it.
- **Tests are already at the interface.** The only production caller is the admin, and most of
  the cluster's tests cross only `DiscoveryApprovalService`.
- **The IP rule is two layers on purpose.** The approval policy checks ownership pre-flight
  against the locked snapshot, with batch-level checks, while `HardwareIPOwnershipService`
  enforces it against live rows at save time. `DiscoveryService._get_conflicting_ips` is a
  different rule again: a lock-free pre-filter that skips candidates owned by another
  manufacturer during scanning.

Reconsider this if a defect traces to a cross-module ordering assumption in the cluster, or if a
second caller appears and the five-module interface starts leaking.

## Prior requests

- #467: "evaluate merging the discovery approval modules"
