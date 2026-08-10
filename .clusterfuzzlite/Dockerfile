FROM gcr.io/oss-fuzz-base/base-builder-python

# Install uv directly to comply with project policies (no pip)
RUN curl -LsSf https://astral.sh/uv/0.5.10/install.sh | env UV_VERSION=0.5.10 UV_INSTALL_DIR=/usr/local/bin sh

COPY . $SRC/django-micboard
WORKDIR $SRC/django-micboard
COPY .clusterfuzzlite/build.sh $SRC/
