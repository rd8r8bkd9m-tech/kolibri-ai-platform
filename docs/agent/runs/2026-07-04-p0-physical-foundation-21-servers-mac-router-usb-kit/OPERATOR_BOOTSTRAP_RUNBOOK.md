# OPERATOR_BOOTSTRAP_RUNBOOK.md

## Bootstrap a New Command Node

### Prerequisites
- SSH access to Home (178.207.11.90:2222)
- Deploy key (Kolibri SSH Key)
- Control Plane URL: http://10.99.0.1:9101

### Steps
1. Copy SSH key to new machine
2. Add SSH config entries for all 21 servers
3. Verify SSH access: `ssh kolibri-home "hostname"`
4. Verify Control Plane: `curl http://10.99.0.1:9101/v1/health`
5. Open NOC: `ssh kolibri-home "curl http://127.0.0.1:8181/"`
6. Test task submission: `curl -X POST http://10.99.0.1:9101/v1/tasks -d '{"kind":"owner_remote_task","priority":"P0","required_capability":"generic_implementation","runner":"mimo","envelope":{"prompt":"echo test"}}'`

### Emergency Recovery
If Mac is offline:
1. SSH to Home from any trusted machine
2. Check Control Plane health
3. Check Redis: `redis-cli ping`
4. Check factory-control: `pgrep -fa factory-control`
5. Restart if needed: `sudo systemctl restart kolibri-factory-control`

### USB Kit Contents
See USB_OPERATOR_KIT_PROFILE.md for full list.
