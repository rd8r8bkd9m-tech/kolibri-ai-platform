# Next

- Produce a canary or deploy next-step only.
- Do not restart the live Agent Host.
- Do not deploy to Home from this task.
- After PR review and merge, run a separate owner-approved deploy task to patch the live Home Agent Host runtime.
- After that deploy task verifies the patched runtime is active, dispatch `P0_HOME_AGENT_HOST_NONEMPTY_ARTIFACT_CONTRACT_CANARY_2026_07_03` to prove empty artifact blocking and manifest-visible non-empty canonical artifacts on Home.
