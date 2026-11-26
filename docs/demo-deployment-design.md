---
title: "How the read-only demo works"
description: "Why the demo is read-only, what its dataset contains, and what the shared account can do."
type: explanation
audience: developer
---
The public demo shows the dashboards and admin to someone with no wireless hardware. It is deliberately read-only: the account it ships with can open every page and change nothing. To run one, see [Deploy the read-only demo](demo-deployment.md).

## Why read-only is the only sensible mode

Saving a chassis, channel, or transmitter fires the hooks in `micboard/model_lifecycle.py`,
which resolve the manufacturer's integration plugin. That plugin expects a live Shure System
API and refuses to work without `SHURE_API_SHARED_KEY`. A writable demo would therefore need
either real credentials or a stubbed integration.

Loading the demo fixture avoids this entirely: Django loads fixtures with `raw=True`, and
every lifecycle hook returns early on a raw save. The demo dataset lands without ever
resolving an integration.

## What gets seeded

`micboard/fixtures/demo.json` holds the structural data — one Shure ULXD4Q receiver in a
recital hall, its four RF channels, four transmitters with varied battery and RF levels,
a monitoring group, and four performer assignments. Its primary keys are committed, so
reloading it updates the same rows instead of creating duplicates.

Two things cannot be expressed in a fixture, so `seed_demo_data` handles them:

- **Telemetry** is written relative to the current time. A fixture's timestamps would freeze,
  and the demo would report devices last seen months ago.
- **The read-only account's password** comes from `MICBOARD_DEMO_PASSWORD`. Without it the
  account is not created at all, so a deployment cannot accidentally publish a staff login
  with a guessable default.

```bash
uv run --no-sync python manage.py seed_demo_data
MICBOARD_DEMO_PASSWORD=... uv run --no-sync python manage.py seed_demo_data
```

The command is idempotent and runs on every container start.

It refuses to run against a database holding wireless hardware that the fixture does not
own. The fixture's primary keys start at 900001 and `loaddata` overwrites whatever occupies
the keys it carries, so this check keeps the command from quietly replacing real records.

## What the account can and cannot do

`seed_demo_data` puts the `demo` user in a `Demo (read-only)` group holding every `view_`
permission for `micboard` and `micboard_multitenancy`, and nothing else. The account is
`is_staff` so the admin opens, and never `is_superuser`. Every redeploy reapplies this, so an
account that somehow gained privileges loses them again on the next start, and a rotated
password takes effect immediately.

Removing `MICBOARD_DEMO_PASSWORD` and redeploying **retires** the account: the next start
deactivates it, strips its staff flag, and sets an unusable password. The environment is the
only thing that keeps the login alive.

With `MICBOARD_DEMO_MODE=True` the deployment also overrides Django's two password-change
routes, under `admin/` and `accounts/`, with a permission error. Everyone shares one account,
so a visitor changing its password would lock out everyone else until the next redeploy.

Background polling is left off. With no `SHURE_API_SHARED_KEY` configured there is nothing to
poll, and the demo's telemetry is seeded rather than collected.
