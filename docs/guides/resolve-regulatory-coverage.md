---
title: "Resolve missing regulatory coverage"
description: "Audit regulatory coverage and fix chassis or channels that lack frequency data."
type: how-to
audience: staff
---
Use this when the Django admin shows **Missing coverage** for a chassis band plan or an RF channel. How the check works is explained in [Regulatory coverage monitoring](regulatory-coverage-monitoring.md).

## Audit

```bash
uv run --no-sync python manage.py audit_regulatory_coverage
```

The command lists active chassis whose location has no regulatory domain, chassis with no band plan, chassis whose band plan is not covered, and active RF channels whose frequency is not covered. Add `--fix` to fill a missing band plan from the chassis model code where one can be inferred.

## Fix what it reports

1. **No regulatory domain.** In the admin, open the chassis location (building) and set its `regulatory_domain` or country.
2. **No band plan.** Set one on the chassis. See [Set a chassis band plan](band-plan-auto-population.md).
3. **Band plan or frequency not covered, European region.** Import the EFIS data:

   ```bash
   uv run --no-sync python manage.py import_efis_regulations --force
   ```

   Without `--force`, the import is skipped when the data is under 30 days old.
4. **Not covered, other region.** In the admin, open **Regulatory Domains**, add or choose the domain (for example `FCC`), and add frequency bands under it.
5. Run the audit again to confirm.

## Run the audit on a schedule

Run the audit from your scheduler and keep its output for review, for example from cron:

```bash
0 6 * * * cd /path/to/project && uv run --no-sync python manage.py audit_regulatory_coverage >> /var/log/micboard/regulatory_audit.log 2>&1
```
