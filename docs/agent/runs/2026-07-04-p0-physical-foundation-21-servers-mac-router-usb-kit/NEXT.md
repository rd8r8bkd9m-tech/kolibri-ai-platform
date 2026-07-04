# NEXT.md

## Immediate Next Tasks
1. Update ops/factory_registry.py with new asset classes
2. Add tests for 21 canonical servers
3. Create draft PR
4. Restart agent-host on paris and agent-03
5. Restore agent-10 connectivity

## Architecture Decisions
- Physical servers ≠ logical workers
- Mac is command_node, not execution
- Router is network_node, not agent
- USB kit is operator_kit, not worker
- agent-10 quarantined until proven
