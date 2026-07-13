Kolibri AI OS V2.1 Release Candidate

Local development:
  ./scripts/dev.sh

Validation:
  ./scripts/validate.sh

Complete release evidence:
  ./scripts/release-check.sh

Factory canary:
  Start the API with KOLIBRI_NODE_JOIN_TOKEN and KOLIBRI_OWNER_ACCESS_TOKEN,
  then run ./scripts/factory-canary.sh.

Controlled single-server deployment:
  cp .env.example .env
  replace every placeholder secret
  docker compose up --build -d

This candidate is not evidence of a physical 21-node production campaign.
See README.ru.md and docs/release/V2_1_BUILD_STATUS.md.
