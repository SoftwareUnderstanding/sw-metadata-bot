ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# git is required to resolve the metacheck git source dependency
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Copy the project into the image
COPY . /app

# Disable development dependencies
ENV UV_NO_DEV=1

# Sync the project into a new environment, asserting the lockfile is up to date.
WORKDIR /app
RUN uv sync --locked

CMD ["uv", "run", "sw-metadata-bot", "--help"]
