# Dockerfile for django-micboard demo
# Base: Debian Trixie slim
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    ca-certificates \
    procps \
 && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project definition
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy the project into the image. In compose we'll mount the repo over /app for development.
COPY . /app

# Copy entrypoint
COPY demo/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
