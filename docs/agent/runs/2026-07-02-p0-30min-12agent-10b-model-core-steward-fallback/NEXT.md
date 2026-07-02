# Next

- Wire authenticated model-node health into registered node heartbeats so `/v1/models` reflects real serving readiness.
- Add a guarded integration test for the HTTP `/v1/models` response once the test harness can safely stub Redis.
- Define the eventual authenticated `/v1/responses` model-node handoff contract separately before enabling live generation.

