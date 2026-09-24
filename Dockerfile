# Container image for the public read-only demo. See docs/demo-deployment.md.
#
# The image carries the example project, not a production deployment of the app: the
# reusable app itself is consumed as a dependency by host projects, which bring their own
# settings and server.
FROM python:3.14-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56 AS base

# uv is the only supported way to install dependencies in this project.
# renovate: datasource=docker depName=ghcr.io/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=example_project.settings \
    MICBOARD_DEMO_MODE=true

WORKDIR /app

# Dependencies resolve from the lockfile in their own layer, so application edits do not
# invalidate the install.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project \
    --extra demo \
    --extra standard \
    --extra fixtures \
    --extra media

COPY micboard ./micboard
COPY example_project ./example_project
COPY templates ./templates
COPY manage.py ./
RUN uv sync --locked --no-editable \
    --extra demo \
    --extra standard \
    --extra fixtures \
    --extra media

# Collected once at build time; the running container needs no writable static directory.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

# Run unprivileged. The demo holds no secrets beyond its database URL, but a web process
# has no reason to own its own source tree either.
RUN useradd --create-home --shell /usr/sbin/nologin demo \
    && chown -R demo:demo /app
USER demo

EXPOSE 8000

# Migrations and seeding run per start rather than per build, because they need the
# database that only exists at run time. Both are idempotent.
CMD ["sh", "-c", "python manage.py migrate --noinput \
    && python manage.py seed_demo_data \
    && exec gunicorn example_project.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --threads 4 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -"]
