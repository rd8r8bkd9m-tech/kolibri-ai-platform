# Risk Register

1. Frontend/backend route drift: frontend references `/api/knowledge` and `/rag/search`, but the scanned backend route map does not clearly implement both in the main app.
2. Hardcoded mesh URLs in `backend/pipeline.py` reduce environment portability and failover.
3. Duplicated organism implementation in `infra/network/api.py` and `infra/network/organism.py` can drift.
4. Telegram gateway has high complexity in one file, increasing regression risk.
5. Secret-bearing runtime configuration cannot be represented in digest without a dedicated redacted inventory process.
6. Some Control Plane node records are stale or degraded; active task node is healthy, but fleet state needs its own operational audit.
7. CI/API status beyond git refs was not queried in this read-only pass.

