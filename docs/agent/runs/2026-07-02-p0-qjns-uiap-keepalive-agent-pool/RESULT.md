# Result

`qjns` and `uiap` now have a deployable safe worker-pool path through Agent Host.

When enabled, Agent Host validates disk, memory, max inflight and MIMO availability before advertising worker capabilities. It posts a `worker_pool` readiness object on register, heartbeat and lease requests, so Control Plane and UI surfaces can show why a node is usable or blocked. Control Plane honors that readiness and will not lease MIMO or generic implementation work to a node that reports `worker_pool.ready=false`.

Safe start on a target host:

```bash
export KOLIBRI_QJNS_UIAP_WORKER_POOL=1
export KOLIBRI_AGENT_MIN_DISK_FREE_GB=5
export KOLIBRI_AGENT_MIN_MEM_AVAILABLE_MB=512
export KOLIBRI_MAX_INFLIGHT=1
scripts/preflight-agent-worker-pool.sh /opt/kolibri-ai-platform
sudo systemctl restart kolibri-agent-host
```

Rollback:

```bash
unset KOLIBRI_QJNS_UIAP_WORKER_POOL
sudo systemctl restart kolibri-agent-host
```

or set `KOLIBRI_QJNS_UIAP_WORKER_POOL=0` in `/etc/kolibri-agent-host.env` and restart the service.
