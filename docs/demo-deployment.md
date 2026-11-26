---
title: "Deploy the read-only demo"
description: "Run the public read-only demo on free, scale-to-zero platforms."
type: how-to
audience: staff
---
Run the public, read-only demonstration of django-micboard at no cost, on platforms that scale to zero when nobody is looking at it. How the demo is built and what its account can do is explained in [How the read-only demo works](demo-deployment-design.md).

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

