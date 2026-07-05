# SSH_ACCESS_MATRIX.md

**Date:** 2026-07-04T22:20:00Z
**Verified:** Live SSH from MacBook

| alias | target | user | jump_path | result | hostname | agent_host | blocker |
|-------|--------|------|-----------|--------|----------|------------|---------|
| kolibri-home | 178.207.11.90:2222 | ladik | direct | OK | plastilin | active | — |
| kolibri-main | 104.253.43.117 | root | direct | OK | kolibri-main-api | active | — |
| kolibri-primary-codex | 78.17.4.108 | root | direct | OK | kolibri | active | — |
| kolibri-uiap | 31.57.26.151 | root | direct | OK | kolibri-rag-knowledge | active | — |
| kolibri-qjns | 217.60.63.97 | root | direct | OK | kolibri-tools-executor | active | — |
| kolibri-9fts | 94.183.235.154 | root | direct | OK | kolibri-inference-recovery | active | — |
| kolibri-new | 109.248.161.39 | root | direct | OK | kolibri-worker-backup | active | — |
| server-kfrm | 217.60.63.31 | root | direct | OK | server-kfrm | active | — |
| reserve242 | 31.57.26.242 | root | direct | OK | kolibri-qa-security | active | — |
| hostvds-highload | 45.38.139.182 | root | direct | OK | kolibri-ci-build-highload | active | — |
| hostvds-paris-highload | 95.182.83.60 | root | direct | OK | kolibri-paris-build-reserve | no | agent-host not running |
| hostvds-agent-01 | 31.57.27.128 | root | direct | OK | kolibri-backend-lead | active | — |
| hostvds-agent-02 | 213.232.204.223 | root | direct | OK | kolibri-frontend-design | active | — |
| hostvds-agent-03 | 188.130.206.204 | root | direct | OK | kolibri-infra-network | no | agent-host not running |
| hostvds-agent-04 | 31.59.41.146 | root | direct | OK | kolibri-qa-browser | active | — |
| hostvds-agent-05 | 31.56.196.10 | root | direct | OK | kolibri-security-audit | active | — |
| hostvds-agent-06 | 94.183.236.19 | root | direct | OK | kolibri-docs-knowledge | active | — |
| hostvds-agent-07 | 31.56.225.35 | root | direct | OK | kolibri-formulalm-eval | active | — |
| hostvds-agent-08 | 94.183.229.121 | root | direct | OK | kolibri-rag-eval | active | — |
| hostvds-agent-09 | 45.38.137.104 | root | direct | OK | kolibri-release-canary | active | — |
| hostvds-agent-10 | 217.60.38.191 | root | direct | OK | kolibri-hk-edge-load | active | quarantined |

**Summary:** 21/21 reachable. 2 servers (paris, agent-03) need agent-host restart.
