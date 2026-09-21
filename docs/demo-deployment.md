---
title: "Read-Only Demo Deployment"
---
This page describes how to run the public, read-only demonstration of django-micboard at no
cost, on platforms that scale to zero when nobody is looking at it.

The demo exists to show the dashboards and admin to someone who has no wireless hardware. It
is deliberately read-only: the account it ships with can open every page and change nothing.

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

## Platform choice

Both of these have a perpetual free tier and need no payment method:

| Component | Service | Idle behaviour |
| --- | --- | --- |
| Web | Render free web service | Spins down after 15 minutes; cold start is 30 seconds or more |
| Database | Neon free Postgres | Scales compute to zero after 5 minutes; wakes in about 570 ms |

Do not point an uptime pinger at the demo to keep it warm. It burns the monthly instance
hours the free tier grants and defeats the purpose of scaling to zero. Set expectations about
the cold start instead.

Managed Postgres is not optional. Every platform above runs the container on an ephemeral
filesystem, so the SQLite database this project uses by default would be discarded, and
recreated empty, on each cold start.

## Deploying

1. **Create the database.** Make a Neon project and copy its pooled connection string.
2. **Create the web service.** Point Render at this repository with Docker as the runtime; the
   `Dockerfile` at the repository root builds the demo image. It collects static files at
   build time, then migrates and seeds at start.
3. **Set the environment.**

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | The Neon connection string. `DJANGO_DATABASE_URL` is also accepted and wins if both are set |
   | `DJANGO_SECRET_KEY` | A fresh random value, not the development default |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_ALLOWED_HOSTS` | The deployment hostname |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` plus the deployment hostname |
   | `DJANGO_BEHIND_TLS_PROXY` | `True` |
   | `MICBOARD_DEMO_PASSWORD` | The read-only account's password |
   | `MICBOARD_DEMO_MODE` | `True`, which disables password changes for the shared account |

   `DJANGO_BEHIND_TLS_PROXY` tells Django that the platform terminated TLS at its proxy, which
   it needs before it will set secure cookies or accept an admin login.

4. **Visit the site** and sign in as `demo` with the password above.

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
