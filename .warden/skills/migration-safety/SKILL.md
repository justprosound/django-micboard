---
name: migration-safety
description: Review Django migrations for zero-downtime safety and project policy compliance
allowed-tools: Read Grep Glob
---

Review Django migration files for safety and compliance with project policies.

## Critical Rules

1. **Never edit existing migrations** — Files in `micboard/migrations/` must never be modified, deleted, or manually patched. Only new migration files generated via `makemigrations` are allowed.

2. **No ALTER of existing migration files** — If a migration needs to be changed, create a new migration that reverses and reapplies the change, or create a data migration.

## Zero-Downtime Migration Rules (PostgreSQL)

3. **Adding a NOT NULL column** — Must use `SeparateDatabaseAndState` two-file split pattern:
   - Migration 1: Add column as nullable, run `RunPython` to backfill data
   - Migration 2: `AlterField` to set NOT NULL
   - OR use `db_default` (Django 5.0+) for columns with server-side defaults

4. **Dropping a column** — Must use `SeparateDatabaseAndState`:
   - Migration 1: Remove column from state (Django no longer knows about it) but keep in DB
   - Migration 2 (after deploy): Remove from actual DB schema

5. **Renaming a column** — Must NOT be done in a single migration. Instead:
   - Add new column with same data
   - Dual-write to both columns in application code
   - Backfill data
   - Remove old column

6. **Adding an index** — Must use `AddIndexConcurrently` to avoid table locks.

7. **Adding a foreign key** — Must use `SeparateDatabaseAndState` with `FK NOT VALID` then `VALIDATE CONSTRAINT` to avoid long exclusive locks.

8. **Large table alterations** — Must consider `lock_timeout` for any operation on tables with >100k rows.

## Check for These Anti-Patterns

- `RunSQL` without `atomic=False` (can cause locks)
- `RunPython` operations that load the entire model class (use historical models)
- Adding `unique=True` to an existing column without a concurrent unique index
- Removing a field that's still referenced in other migrations
- Elidable migrations that could be squashed but aren't

## Report Format

For each issue found, report:
- **Severity**: `critical` (downtime risk), `high` (policy violation), `medium` (optimization opportunity)
- **File and line**
- **What the risk is**
- **How to fix it** (concrete migration pattern)
