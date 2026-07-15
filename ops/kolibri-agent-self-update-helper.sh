#!/bin/bash
# Kolibri Agent Host self-update helper
# Runs as root to replace the agent host binary and restart the service.
# The agent host writes the new binary to STAGING_DIR, then triggers this script.
set -euo pipefail

STAGING_DIR="/var/lib/kolibri-agent/pending-update"
TARGET="/usr/local/bin/kolibri-agent-host"
ENV_FILE="/etc/kolibri-agent-host.env"

if [ ! -d "$STAGING_DIR" ] || [ ! -f "$STAGING_DIR/kolibri-agent-host" ]; then
    echo "No pending update found"
    exit 0
fi

echo "Applying agent host update..."

# Backup current
cp "$TARGET" "${TARGET}.bak"

# Replace
cp "$STAGING_DIR/kolibri-agent-host" "$TARGET"
chmod 755 "$TARGET"

# Update capabilities if provided
if [ -f "$STAGING_DIR/capabilities" ]; then
    NEW_CAPS=$(cat "$STAGING_DIR/capabilities")
    sed -i "s/KOLIBRI_AGENT_CAPABILITIES=.*/KOLIBRI_AGENT_CAPABILITIES=${NEW_CAPS}/" "$ENV_FILE"
    echo "Updated capabilities: $NEW_CAPS"
fi

# Cleanup staging
rm -rf "$STAGING_DIR"

# Restart agent host
systemctl restart kolibri-agent-host.service
echo "Agent host updated and restarted"
