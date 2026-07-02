# NEXT

Next exact task:

`P1_FACTORY_QUEUE_RECONCILER_ATOMICITY_AND_RUNTIME_CANARY_2026_07_02`

Objective:

Add an optional periodic control-plane reconciler loop or Redis transaction/Lua-backed atomic queue move for lease expiry, then run a live canary against a scoped Redis namespace to verify duplicate-free concurrent lease expiry under multiple worker polls.

Exact repair command for full-suite environment blocker:

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m pytest
```

