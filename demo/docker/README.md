Docker demo for django-micboard

Quickstart (requires Docker and docker-compose)

From repository root:

```bash
cd demo/docker
# Build the image (first time)
docker compose build
# Run the demo
docker compose up
```

Notes

- The compose file mounts the repository into /app so edits on the host reflect in the container during development.
- The entrypoint installs requirements if missing, runs migrations, creates a demo superuser and seeds demo data before running the server.
- If you want to run custom management commands, use:

```bash
docker compose run --rm micboard-demo python manage.py <command> --settings=demo.settings
```

## Configuration

The demo uses a `.env` file for environment variables. You can customize it:

```bash
# Copy the example
cp .env .env.local
# Edit .env.local with your settings
# Then run with: docker compose --env-file .env.local up
```

## Integrating with External Shure System API

The demo container can connect to an external Shure System API running on your host or another platform. By default, it uses `http://host.docker.internal:10000` to reach services on the host machine.

To override the API URL:

```bash
SHURE_API_BASE_URL=http://your-api-host:port docker compose up
```

Or edit the `.env` file:

```
SHURE_API_BASE_URL=http://your-api-host:port
```

This allows quick validation of the micboard app against real or mock Shure APIs on different platforms.
