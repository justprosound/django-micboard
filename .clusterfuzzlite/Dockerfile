FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:6b2b3a7e4a2da50de47f94925cffbe34747e1aae4f33d7f07ba6c681dd648b23

# Install uv directly to comply with project policies (no pip)
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

COPY . $SRC/django-micboard
WORKDIR $SRC/django-micboard
COPY .clusterfuzzlite/build.sh $SRC/
