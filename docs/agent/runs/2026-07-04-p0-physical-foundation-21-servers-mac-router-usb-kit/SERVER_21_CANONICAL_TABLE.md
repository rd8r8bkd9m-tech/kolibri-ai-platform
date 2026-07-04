# SERVER_21_CANONICAL_TABLE.md

**Date:** 2026-07-04T22:20:00Z
**Count:** 21 canonical physical servers

| # | node_id | hostname | role | internal_ip | external_ip | ssh_alias | mimo | agent_host | codex | lifecycle |
|---|---------|----------|------|-------------|-------------|-----------|------|------------|-------|-----------|
| 1 | home | plastilin | hybrid | 10.99.0.1 | 178.207.11.90 | kolibri-home | yes | yes | yes | active |
| 2 | main | kolibri-main-api | control | 10.99.0.2 | 104.253.43.117 | kolibri-main | yes | yes | yes | active |
| 3 | primary-candidate | kolibri | hybrid | 10.99.0.10 | 78.17.4.108 | kolibri-primary-codex | yes | yes | yes | active |
| 4 | uiap | kolibri-rag-knowledge | rag | 10.99.0.3 | 31.57.26.151 | kolibri-uiap | yes | yes | yes | active |
| 5 | qjns | kolibri-tools-executor | tool | 10.99.0.4 | 217.60.63.97 | kolibri-qjns | yes | yes | yes | active |
| 6 | 9fts | kolibri-inference-recovery | model | 10.99.0.5 | 94.183.235.154 | kolibri-9fts | yes | yes | yes | active |
| 7 | new | kolibri-worker-backup | reserve | 10.99.0.6 | 109.248.161.39 | kolibri-new | yes | yes | yes | active |
| 8 | server-kfrm | server-kfrm | execution | 10.99.0.7 | 217.60.63.31 | server-kfrm | yes | yes | yes | active |
| 9 | reserve242 | kolibri-qa-security | reserve | — | 31.57.26.242 | reserve242 | yes | yes | yes | active |
| 10 | highload | kolibri-ci-build-highload | execution | — | 45.38.139.182 | hostvds-highload | yes | yes | yes | active |
| 11 | paris | kolibri-paris-build-reserve | reserve | — | 95.182.83.60 | hostvds-paris-highload | yes | no | yes | active |
| 12 | agent-01 | kolibri-backend-lead | execution | — | 31.57.27.128 | hostvds-agent-01 | yes | yes | yes | active |
| 13 | agent-02 | kolibri-frontend-design | execution | — | 213.232.204.223 | hostvds-agent-02 | yes | yes | yes | active |
| 14 | agent-03 | kolibri-infra-network | execution | — | 188.130.206.204 | hostvds-agent-03 | yes | no | yes | active |
| 15 | agent-04 | kolibri-qa-browser | execution | — | 31.59.41.146 | hostvds-agent-04 | yes | yes | yes | active |
| 16 | agent-05 | kolibri-security-audit | execution | — | 31.56.196.10 | hostvds-agent-05 | yes | yes | yes | active |
| 17 | agent-06 | kolibri-docs-knowledge | execution | — | 94.183.236.19 | hostvds-agent-06 | yes | yes | yes | active |
| 18 | agent-07 | kolibri-formulalm-eval | model | — | 31.56.225.35 | hostvds-agent-07 | yes | yes | yes | active |
| 19 | agent-08 | kolibri-rag-eval | rag | — | 94.183.229.121 | hostvds-agent-08 | yes | yes | yes | active |
| 20 | agent-09 | kolibri-release-canary | execution | — | 45.38.137.104 | hostvds-agent-09 | yes | yes | yes | active |
| 21 | agent-10 | kolibri-hk-edge-load | execution | — | 217.60.38.191 | hostvds-agent-10 | yes | yes | yes | quarantined |

## Notes
- agent-10 quarantined: provider_network_unreachable unless proven otherwise
- paris/agent-03: agent-host not running (needs restart)
- All 21 servers have mimo and codex available
- Internal IPs only available for VPN-connected servers (home through new)
