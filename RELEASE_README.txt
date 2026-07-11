Vista OS 11.1 Product Release

Local start:
  ./scripts/dev-fone.sh

Validation:
  python3 -m pip install -r backend/requirements-dev.txt
  ./scripts/validate-fone.sh
  ./scripts/release-check.sh

Production:
  cp .env.example .env
  # Replace all placeholder secrets
  ./scripts/deploy-vista-server.sh

See README.ru.md and docs/release/VISTA_OS_11_1_BUILD_REPORT.md.
