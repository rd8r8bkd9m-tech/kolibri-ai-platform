# NEXT.md

## Immediate Next Tasks

1. **Integrate ledgers into factory_control.py** — Wire claims/evidence/verdict into task lifecycle
2. **Automate anti-agent review** — Spawn anti-agent subagent for every P0 task
3. **Fix running index drift** — Rebuild phantom running tasks
4. **Restore VPN tunnels** — 9fts/uiap/new connectivity
5. **Deploy Truth Factory to production** — Make it the default workflow

## Architecture Decisions

- Truth Factory is a layer, not a replacement
- Anti-agent is a role, not a separate system
- Evidence is required for every claim
- Verdicts drive next tasks
- Owner summary is always short and clear
