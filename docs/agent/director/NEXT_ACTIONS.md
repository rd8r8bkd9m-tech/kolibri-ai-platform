# Director Next Actions

1. Locate authoritative Factory Control listener.
2. Restore `/v1/health` without queue deletion.
3. Run gateway health against restored Control Plane.
4. Submit one read-only task through gateway.
5. Collect artifact and update `START_FACTORY_MVP_EXECUTION_PROOF.md`.
