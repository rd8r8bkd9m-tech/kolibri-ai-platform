#!/bin/bash
# Kolibri OS — Unified Server Provisioning Script
# Usage: ./scripts/provision-server.sh --ip IP --name NAME --role ROLE [--vpn-ip VPN_IP] [--api-port PORT]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

IP=""
NAME=""
ROLE="execution"
VPN_IP=""
API_PORT=8001
SSH_KEY="~/.ssh/id_ed25519"
VERIFY=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --ip) IP="$2"; shift ;;
        --name) NAME="$2"; shift ;;
        --role) ROLE="$2"; shift ;;
        --vpn-ip) VPN_IP="$2"; shift ;;
        --api-port) API_PORT="$2"; shift ;;
        --ssh-key) SSH_KEY="$2"; shift ;;
        --verify) VERIFY=true ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

if [ "$VERIFY" = true ]; then
    echo -e "${GREEN}Verifying $NAME ($IP)...${NC}"
    ssh -o ConnectTimeout=5 -i $SSH_KEY root@$IP "hostname; systemctl is-active kolibri-agent-api 2>/dev/null || echo 'not running'" 2>&1
    exit 0
fi

if [ -z "$IP" ] || [ -z "$NAME" ]; then
    echo "Usage: $0 --ip IP --name NAME [--role ROLE] [--vpn-ip VPN_IP] [--api-port PORT]"
    exit 1
fi

echo -e "${GREEN}Provisioning $NAME ($IP) as $ROLE...${NC}"

# Step 1: SSH connect
echo -e "${YELLOW}Step 1: SSH connect...${NC}"
ssh -o ConnectTimeout=10 -i $SSH_KEY root@$IP "echo 'SSH OK'" || { echo -e "${RED}SSH failed${NC}"; exit 1; }

# Step 2: Install dependencies
echo -e "${YELLOW}Step 2: Installing dependencies...${NC}"
ssh -o ConnectTimeout=30 -i $SSH_KEY root@$IP "apt-get update -qq && apt-get install -y -qq python3 python3-pip wireguard-tools 2>/dev/null" || true

# Step 3: Configure WireGuard
if [ -n "$VPN_IP" ]; then
    echo -e "${YELLOW}Step 3: Configuring WireGuard ($VPN_IP)...${NC}"
    ssh -o ConnectTimeout=10 -i $SSH_KEY root@$IP "
cat > /etc/wireguard/wg-kolibri.conf << EOF
[Interface]
Address = $VPN_IP/24
ListenPort = 51830
PrivateKey = \$(wg genkey)

[Peer]
PublicKey = \$(echo 'plNRkjwcnlJThsRaxzJJTy8eILThBl19fwwmofvm70w=')
Endpoint = 192.168.88.210:51830
AllowedIPs = 10.99.0.0/24
PersistentKeepalive = 25
EOF
systemctl enable wg-quick@wg-kolibri && systemctl start wg-quick@wg-kolibri
" || { echo -e "${RED}WireGuard failed${NC}"; exit 1; }
fi

# Step 4: Install API agent service
echo -e "${YELLOW}Step 4: Installing API agent...${NC}"
ssh -o ConnectTimeout=10 -i $SSH_KEY root@$IP "
cat > /etc/systemd/system/kolibri-agent-api.service << EOF
[Unit]
Description=Kolibri Agent API
After=network.target

[Service]
Type=simple
Environment=KOLIBRI_NODE_ID=$NAME
Environment=KOLIBRI_CONTROL_URL=http://192.168.88.210:9101
ExecStart=/usr/local/bin/mimo serve --port $API_PORT
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable kolibri-agent-api && systemctl start kolibri-agent-api
" || { echo -e "${RED}Agent install failed${NC}"; exit 1; }

# Step 5: Register in Control Plane
echo -e "${YELLOW}Step 5: Registering in Control Plane...${NC}"
curl -s --connect-timeout 5 -X POST http://192.168.88.210:9101/v1/nodes/register \
    -H "Content-Type: application/json" \
    -d "{\"node_id\":\"$NAME\",\"hostname\":\"$NAME\",\"role\":\"$ROLE\",\"capabilities\":[\"mimo\",\"generic_implementation\"]}" > /dev/null

# Step 6: Verify
echo -e "${YELLOW}Step 6: Verifying...${NC}"
ssh -o ConnectTimeout=5 -i $SSH_KEY root@$IP "systemctl is-active kolibri-agent-api" 2>&1 | grep -q "active" && \
    echo -e "${GREEN}✓ $NAME provisioned successfully${NC}" || \
    echo -e "${RED}✗ $NAME verification failed${NC}"

echo -e "${GREEN}Done!${NC}"
