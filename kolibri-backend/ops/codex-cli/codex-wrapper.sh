#!/bin/sh
set -eu

# Keep the owner-authorized Codex session on Home. These files contain runtime
# configuration only; credentials remain in Codex's own protected auth store.
set -a
if [ -r /etc/kolibri/codex-cli.env ]; then
    . /etc/kolibri/codex-cli.env
fi
if [ -r /etc/kolibri/codex-cli/proxy.env ]; then
    . /etc/kolibri/codex-cli/proxy.env
fi
set +a

CODEX_BINARY=${CODEX_CLI_BINARY:-/usr/local/bin/codex}
exec "$CODEX_BINARY" "$@"
