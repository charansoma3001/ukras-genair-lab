# linux/amd64 image. Renders AI2-THOR headlessly with Xvfb + software GL.

# Builder: install deps with uv, build the MkDocs Guide.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY mkdocs.yml ./
COPY docs ./docs
COPY scripts ./scripts
RUN uv run mkdocs build

# Runtime.
FROM python:3.11-slim-bookworm AS runtime

# Xvfb + the X/GL libraries the THOR Unity build needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        xauth \
        x11-utils \
        libgl1 \
        libgl1-mesa-dri \
        libglu1-mesa \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libxi6 \
        libxrandr2 \
        libxcursor1 \
        libxinerama1 \
        libxfixes3 \
        libxcomposite1 \
        libxdamage1 \
        libxtst6 \
        libasound2 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    PORT=8001

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/web /app/web
COPY src ./src
COPY web/index.html web/styles.css web/app.js ./web/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Bake the THOR build into the image so first boot is instant and offline.
# PREBAKE_THOR=0 skips it (e.g. when building under emulation on arm64).
ARG PREBAKE_THOR=1
RUN if [ "$PREBAKE_THOR" = "1" ]; then \
        xvfb-run -a -s "-screen 0 1280x1024x24" \
            python -c "from ai2thor.controller import Controller; c=Controller(scene='FloorPlan1', width=300, height=300); c.stop()" \
        || (echo 'pre-bake failed, will download on first run'; rm -rf /root/.ai2thor/releases /root/.ai2thor/tmp); \
    else \
        echo 'pre-bake skipped'; \
    fi

# Mount these to keep student edits across restarts.
VOLUME ["/app/prompts", "/app/tasks"]

EXPOSE 8001
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
