ARG NODE_IMAGE=node:24.18.0-bookworm
ARG PYTHON_IMAGE=python:3.12.13-bookworm

FROM ${NODE_IMAGE} AS node_runtime

FROM ${PYTHON_IMAGE}

COPY --from=node_runtime /usr/local/ /usr/local/

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      git \
      systemd \
    && rm -rf /var/lib/apt/lists/* \
    && node --version \
    && npm --version \
    && python --version \
    && systemd-analyze --version

ENV NEXT_TELEMETRY_DISABLED=1
ENV EXPO_NO_TELEMETRY=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace

