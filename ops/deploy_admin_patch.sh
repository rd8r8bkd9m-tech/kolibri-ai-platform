#!/bin/bash
# Deploy patched agent host to all Kolibri servers.
# Run from Home: bash /tmp/deploy_admin_patch.sh
set -euo pipefail

PATCH="/tmp/patch_agent_host_admin.py"
REMOTE_AGENT="/usr/local/bin/kolibri-agent-host"
ENV_FILE="/etc/kolibri-agent-host.env"
PASS="Busya26"

# Servers accessible via SSH (from Home)
# Format: ssh_alias
SERVERS=(
    agent01 agent02 agent03 agent04 agent05
    agent06 agent07 agent08 agent09 agent10
    main qjns new 9fts uiap
    kfrm highload paris primary reserve242
)

echo "=== Deploying admin patch to ${#SERVERS[@]} servers ==="

for server in "${SERVERS[@]}"; do
    echo -n "  $server ... "
    
    # Check if reachable
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$server" "echo ok" 2>/dev/null; then
        echo "UNREACHABLE"
        continue
    fi
    
    # Upload patch script
    scp -o ConnectTimeout=5 "$PATCH" "$server:/tmp/patch_agent_host_admin.py" 2>/dev/null
    
    # Check if already patched
    if ssh -o ConnectTimeout=5 "$server" "grep -q 'admin_exec' $REMOTE_AGENT 2>/dev/null" 2>/dev/null; then
        echo "ALREADY PATCHED"
        continue
    fi
    
    # Backup and patch
    ssh -o ConnectTimeout=5 "$server" "
        echo '$PASS' | sudo -S cp $REMOTE_AGENT ${REMOTE_AGENT}.bak 2>/dev/null
        echo '$PASS' | sudo -S python3 /tmp/patch_agent_host_admin.py $REMOTE_AGENT 2>&1
    " 2>/dev/null
    
    # Add admin capabilities to env
    ssh -o ConnectTimeout=5 "$server" "
        if grep -q 'KOLIBRI_AGENT_CAPABILITIES' $ENV_FILE 2>/dev/null; then
            echo '$PASS' | sudo -S sed -i 's/KOLIBRI_AGENT_CAPABILITIES=.*/KOLIBRI_AGENT_CAPABILITIES=generic_implementation,read_only_probe,admin_exec,admin_service,admin_git,admin_rotate_keys/' $ENV_FILE 2>/dev/null
        fi
    " 2>/dev/null
    
    # Restart agent host
    ssh -o ConnectTimeout=5 "$server" "
        echo '$PASS' | sudo -S systemctl restart kolibri-agent-host.service 2>/dev/null
    " 2>/dev/null
    
    echo "OK"
done

echo "=== Done ==="
