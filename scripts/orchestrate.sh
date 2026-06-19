#!/bin/bash
# Kolibri AI — Server Orchestration Script
# MacBook as orchestrator, 6 servers with MiMo Code as agents
# Usage: ./scripts/orchestrate.sh <command> [server] [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/infra/network/config.json"
LOG_DIR="$PROJECT_DIR/logs/orchestrate"
mkdir -p "$LOG_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVERS=("home" "main" "uiap" "qjns" "9fts" "kolibri" "reserve242" "hostvds-highload")

get_server_info() {
    local server="$1"
    local key="$2"
    python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d['servers']['$server']['$key'])" 2>/dev/null || echo ""
}

ssh_exec() {
    local server="$1"
    shift
    local alias=$(get_server_info "$server" "ssh_alias")
    local cmd="$*"
    
    if [ "$server" = "home" ]; then
        ssh -o ConnectTimeout=10 -p 2222 ladik@$(get_server_info "$server" "public_ip") "$cmd" 2>/dev/null
    else
        ssh -o ConnectTimeout=10 "$alias" "$cmd" 2>/dev/null
    fi
}

agent_worktree() {
    local server="$1"
    local task_id="$2"
    if [ "$server" = "home" ]; then
        echo "/srv/kolibri/agent-worktrees/$task_id"
    else
        echo "/opt/kolibri-ai/agent-worktrees/$task_id"
    fi
}

cmd_health() {
    local target="${1:-all}"
    local servers=("$target")
    [ "$target" = "all" ] && servers=("${SERVERS[@]}")
    
    echo -e "${BLUE}=== Kolibri Cluster Health ===${NC}"
    printf "%-12s %-8s %-15s %-10s %-10s\n" "SERVER" "STATUS" "VPN IP" "RAM" "CPU"
    echo "─────────────────────────────────────────────────────────────"
    
    for server in "${servers[@]}"; do
        local vpn_ip=$(get_server_info "$server" "vpn_ip")
        local role=$(get_server_info "$server" "role")
        
        if result=$(ssh_exec "$server" "echo OK" 2>/dev/null); then
            local ram=$(ssh_exec "$server" "free -h 2>/dev/null | awk '/Mem:/{print \$3\"/\"\$2}'" 2>/dev/null || echo "N/A")
            local cpu=$(ssh_exec "$server" "top -bn1 2>/dev/null | grep 'Cpu(s)' | awk '{print \$2}'" 2>/dev/null || echo "N/A")
            printf "%-12s ${GREEN}%-8s${NC} %-15s %-10s %-10s\n" "$server" "ONLINE" "$vpn_ip" "$ram" "${cpu}%"
        else
            printf "%-12s ${RED}%-8s${NC} %-15s %-10s %-10s\n" "$server" "OFFLINE" "$vpn_ip" "-" "-"
        fi
    done
}

cmd_run() {
    local server="$1"
    shift
    local prompt="$*"
    local role=$(get_server_info "$server" "role")
    
    echo -e "${BLUE}[${server}]${NC} Role: ${role}"
    echo -e "${BLUE}[${server}]${NC} Running: ${prompt:0:80}..."
    local task_id="${server}-custom-$(date +%Y%m%d-%H%M%S)"
    
    python3 "$PROJECT_DIR/scripts/mimo_task_runner.py" \
        --log-dir "$LOG_DIR" \
        run-ssh \
        --server "$server" \
        --task-id "$task_id" \
        --task-type "custom" \
        --mode "read_only" \
        --worktree "$(agent_worktree "$server" "$task_id")" \
        --allowed-path "." \
        --prompt "$prompt"
    
    echo -e "${GREEN}[${server}]${NC} Done. Logs: $LOG_DIR"
}

cmd_deploy() {
    local target="${1:-all}"
    local servers=("$target")
    [ "$target" = "all" ] && servers=("${SERVERS[@]}")
    
    echo -e "${BLUE}=== Deploying to: ${servers[*]} ===${NC}"
    
    for server in "${servers[@]}"; do
        echo -e "${YELLOW}[${server}]${NC} Deploying..."
        
        case "$server" in
            main)
                scp -r "$PROJECT_DIR/backend/" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/backend/" 2>/dev/null
                scp -r "$PROJECT_DIR/frontend/" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/frontend/" 2>/dev/null
                ssh_exec "$server" "cd /opt/kolibri-ai/frontend && npm run build && systemctl restart kolibri-ai && nginx -t && systemctl reload nginx"
                ;;
            uiap|qjns)
                scp "$PROJECT_DIR/infra/network/api.py" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/network/api.py" 2>/dev/null
                ssh_exec "$server" "systemctl restart kolibri-network"
                ;;
            9fts)
                scp "$PROJECT_DIR/infra/inference/api.py" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/inference/api.py" 2>/dev/null
                ssh_exec "$server" "systemctl restart kolibri-inference"
                ;;
            home)
                scp -r "$PROJECT_DIR/scripts/training/" "ladik@$(get_server_info "$server" "public_ip"):/opt/kolibri-ai/training/" -P 2222 2>/dev/null
                ;;
            kolibri)
                scp "$PROJECT_DIR/infra/network/worker_service.py" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/network/worker_service.py" 2>/dev/null
                scp "$PROJECT_DIR/infra/network/worker_setup.sh" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/network/worker_setup.sh" 2>/dev/null
                scp "$PROJECT_DIR/scripts/backup.sh" "$(get_server_info "$server" "ssh_alias"):/opt/kolibri-ai/scripts/backup.sh" 2>/dev/null
                ssh_exec "$server" "systemctl restart kolibri-worker"
                ;;
        esac
        
        echo -e "${GREEN}[${server}]${NC} Deployed."
    done
}

cmd_parallel() {
    local prompt="$*"
    local pids=()
    local log_files=()
    
    echo -e "${BLUE}=== Parallel execution across all servers ===${NC}"
    echo -e "${BLUE}Task:${NC} ${prompt:0:100}"
    
    for server in "${SERVERS[@]}"; do
        local log_file="$LOG_DIR/${server}_$(date +%Y%m%d_%H%M%S).log"
        local task_id="${server}-parallel-$(date +%Y%m%d-%H%M%S)"
        log_files+=("$log_file")
        
        (
            python3 "$PROJECT_DIR/scripts/mimo_task_runner.py" \
                --log-dir "$LOG_DIR" \
                run-ssh \
                --server "$server" \
                --task-id "$task_id" \
                --task-type "parallel" \
                --mode "read_only" \
                --worktree "$(agent_worktree "$server" "$task_id")" \
                --allowed-path "." \
                --prompt "$prompt" > "$log_file" 2>&1
            echo -e "${GREEN}[${server}]${NC} Completed"
        ) &
        pids+=($!)
    done
    
    echo -e "${YELLOW}Waiting for all servers...${NC}"
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    
    echo -e "${GREEN}=== All servers completed ===${NC}"
    for i in "${!SERVERS[@]}"; do
        echo -e "\n${BLUE}[${SERVERS[$i]}]${NC} output:"
        cat "${log_files[$i]}" 2>/dev/null | head -20
    done
}

cmd_status() {
    local server="$1"
    echo -e "${BLUE}=== ${server} Status ===${NC}"
    echo -e "${YELLOW}System:${NC}"
    ssh_exec "$server" "uname -a" 2>/dev/null || echo "Cannot connect"
    echo -e "\n${YELLOW}Memory:${NC}"
    ssh_exec "$server" "free -h" 2>/dev/null || echo "N/A"
    echo -e "\n${YELLOW}Disk:${NC}"
    ssh_exec "$server" "df -h /" 2>/dev/null || echo "N/A"
    echo -e "\n${YELLOW}Services:${NC}"
    ssh_exec "$server" "systemctl list-units --type=service --state=running 2>/dev/null | grep kolibri || echo 'No kolibri services'" 2>/dev/null || echo "N/A"
    echo -e "\n${YELLOW}MiMo Code:${NC}"
    local mimo_path=$(get_server_info "$server" "mimo_path")
    ssh_exec "$server" "$mimo_path --version 2>/dev/null || echo 'Not installed'" 2>/dev/null || echo "N/A"
}

cmd_logs() {
    local server="$1"
    local lines="${2:-50}"
    echo -e "${BLUE}=== ${server} Logs (last ${lines}) ===${NC}"
    ssh_exec "$server" "journalctl -u kolibri-ai -u kolibri-network -u kolibri-inference --no-pager -n $lines 2>/dev/null || tail -n $lines /var/log/kolibri*.log 2>/dev/null || echo 'No logs found'"
}

cmd_exec() {
    local server="$1"
    shift
    local cmd="$*"
    echo -e "${BLUE}[${server}]${NC} Executing: $cmd"
    ssh_exec "$server" "$cmd"
}

usage() {
    echo "Kolibri AI — Server Orchestration"
    echo ""
    echo "Usage: $0 <command> [server] [args...]"
    echo ""
    echo "Commands:"
    echo "  health [all|server]           Cluster health check"
    echo "  run <server> <prompt>         Run MiMo Code on specific server"
    echo "  parallel <prompt>             Run task on all servers in parallel"
    echo "  deploy [all|server]           Deploy code to servers"
    echo "  status <server>               Detailed server status"
    echo "  logs <server> [lines]         View server logs"
    echo "  exec <server> <command>       Execute arbitrary command on server"
    echo ""
    echo "Servers: home, main, uiap, qjns, 9fts, kolibri, reserve242, hostvds-highload"
    echo ""
    echo "Examples:"
    echo "  $0 health                     Check all servers"
    echo "  $0 run uiap 'Optimize ChromaDB index'"
    echo "  $0 parallel 'Review code quality'"
    echo "  $0 deploy main                Deploy to main server"
}

case "${1:-help}" in
    health)     cmd_health "${2:-all}" ;;
    run)        cmd_run "${2:?Server required}" "${@:3}" ;;
    parallel)   cmd_parallel "${@:2}" ;;
    deploy)     cmd_deploy "${2:-all}" ;;
    status)     cmd_status "${2:?Server required}" ;;
    logs)       cmd_logs "${2:?Server required}" "${3:-50}" ;;
    exec)       cmd_exec "${2:?Server required}" "${@:3}" ;;
    help|*)     usage ;;
esac
