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

# Create a virtualenv and make its bin available
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install production dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the project into the image. In compose we'll mount the repo over /app for development.
COPY . /app

# Copy entrypoint
COPY demo/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
