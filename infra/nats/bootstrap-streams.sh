#!/usr/bin/env bash
set -euo pipefail

NATS_URL="${NATS_URL:-nats://127.0.0.1:4222}"

nats --server "$NATS_URL" stream add KOLIBRI_EVENTS \
  --subjects "kolibri.>" \
  --retention limits \
  --storage file \
  --max-msgs -1 \
  --max-bytes -1 \
  --max-age 24h || true

nats --server "$NATS_URL" stream add KOLIBRI_TASKS \
  --subjects "kolibri.task.*" \
  --retention limits \
  --storage file \
  --max-msgs -1 \
  --max-bytes -1 \
  --max-age 24h || true

nats --server "$NATS_URL" stream add KOLIBRI_AUDIT \
  --subjects "kolibri.audit.*" \
  --retention limits \
  --storage file \
  --max-msgs -1 \
  --max-bytes -1 \
  --max-age 24h || true

nats --server "$NATS_URL" stream add KOLIBRI_LOGS \
  --subjects "kolibri.log.*" \
  --retention limits \
  --storage file \
  --max-msgs -1 \
  --max-bytes -1 \
  --max-age 24h || true
echo "NATS streams bootstrapped"
