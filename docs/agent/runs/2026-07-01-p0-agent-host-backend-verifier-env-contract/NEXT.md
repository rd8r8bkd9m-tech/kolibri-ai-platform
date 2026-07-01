# Backend Verifier Env Contract Next

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01`

Recommended next steps:

- Use this envelope contract for backend verification tasks that need
  `backend/requirements.txt` plus pytest or other explicit verifier packages.
- Keep backend env setup declarations narrow and auditable; do not add arbitrary
  shell setup hooks unless a separate contract is designed and tested.
- Exercise one real PR review lease with `backend_python_verification_env`
  enabled against a backend test that imports FastAPI.
