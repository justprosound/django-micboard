<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Remove Compat Shim Layer

## Project Description

`micboard/manufacturers/` was a backward-compatibility shim layer. Its `__init__.py` (93 lines) dynamically mirrored `micboard.integrations.*` modules into `sys.modules` under the old `micboard.manufacturers` namespace. The directory also contained `base.py` (98 lines) duplicating abstract base classes (`BaseAPIClient`, `BasePlugin`, `ManufacturerPlugin`) now owned by `micboard/services/common/base/`. Actual plugin implementations lived in `micboard/integrations/shure/` and `micboard/integrations/sennheiser/`. The shim created confusion about canonical import paths, used fragile `sys.modules` manipulation, duplicated class definitions, and added maintenance burden for zero functional value.

## Project Goals

Remove `micboard/manufacturers/` entirely in a single PR. Update all import references from `micboard.manufacturers.*` to `micboard.integrations.*`. Use canonical contracts in `micboard/services/common/base/`; do not create another shared hierarchy or compatibility export. Remove all `sys.modules` patching logic. Verify by grepping for `micboard.manufacturers` across the entire repo. CI fails if any file imports from `micboard.manufacturers`.

## Technical Uncertainties

### Uncertainty #1: Single-PR Migration Across 15-25 Import Sites Without Breaking CI Mid-Migration

**Description:** Estimated 15-25 files imported from `micboard.manufacturers`. A partial migration would break CI (some files using old path, some new). No deprecation window — the shim had existed long enough that actively maintained code should already be migrated. Coordinating all changes atomically across admin, tasks, services, integrations, and tests was the uncertainty.

**Experiments:**
- Pre-migration audit: `grep -r "micboard.manufacturers" --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"` — found 23 import sites across 12 files
- Strategy: create branch, update all 12 files in single commit, delete `micboard/manufacturers/` in same commit, run full test suite
- Risk mitigation: run tests locally before push; if any import missed, CI catches it (fail-fast)

**Results / Learnings / Success:**
- 23 import sites updated in single PR; `micboard/manufacturers/` deleted (191 lines removed)
- CI passed on first push; no follow-up fixes needed
- CI guard added: `grep -r "micboard.manufacturers" micboard/` in pre-commit + CI

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-008 Remove Compat Shim Layer](../../adr/008-remove-compat-shim.md)

### Uncertainty #2: Canonical Contract Location Without Creating New Shared Hierarchy

**Description:** The shim's `base.py` defined `BaseAPIClient`, `BasePlugin`, `ManufacturerPlugin`. These were duplicated in `micboard/services/common/base/`. Removing the shim required confirming `services/common/base/` was the true canonical location and no code still depended on the shim's versions.

**Experiments:**
- Verified: all active integrations (`shure/`, `sennheiser/`) already imported base classes from `services.common.base`
- Verified: `PluginRegistry` constructed plugins using `services.common.base` contracts
- Decision: do not re-export from `integrations/`; callers import directly from `services.common.base`

**Results / Learnings / Success:**
- Single source of truth for plugin contracts at `micboard/services/common/base/`
- No new compatibility layer created
- New integrations follow same pattern: import contracts from `services.common.base`, implement in `integrations/<vendor>/`

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-008 Remove Compat Shim Layer](../../adr/008-remove-compat-shim.md)
- **Related:** [ADR-004 Standardize Manufacturer Plugins](../../adr/004-standardize-manufacturer-plugins.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Audit | ~15% | Import site audit, ADR-008 |
| (engineer) | Migration Implementation | ~30% | 23 import updates, shim deletion |
| (engineer) | CI Guard / Verification | ~15% | Grep check in CI, local test run |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-008 Remove Compat Shim Layer](../../adr/008-remove-compat-shim.md)
- [ADR-004 Standardize Manufacturer Plugins](../../adr/004-standardize-manufacturer-plugins.md)

**PRs:**
- (single migration PR: import updates + shim deletion + CI guard)
