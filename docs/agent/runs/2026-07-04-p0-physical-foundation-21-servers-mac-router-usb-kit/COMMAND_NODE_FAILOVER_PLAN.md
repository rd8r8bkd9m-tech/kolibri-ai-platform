# COMMAND_NODE_FAILOVER_PLAN.md

**Date:** 2026-07-04T22:20:00Z

## Scenario 1: Mac offline
- **What still works:** All factory execution, Home NOC, Control Plane
- **Command node:** Home (primary), Telegram bot
- **How owner sends command:** Telegram, SSH to Home, primary-candidate
- **Recovery:** Fix Mac network, or use another laptop
- **Must not do:** Do not restart factory because Mac is offline

## Scenario 2: Home offline
- **What still works:** Nothing (Control Plane on Home)
- **Command node:** primary-candidate (if CP migrated)
- **How owner sends command:** SSH to primary, rebuild CP
- **Recovery:** Restart Home server, restore CP from Redis backup
- **Must not do:** Do not delete Redis data

## Scenario 3: Router offline
- **What still works:** Internal VPN mesh, factory execution
- **Command node:** Mac via direct IP (if available), Telegram
- **How owner sends command:** Telegram, direct SSH
- **Recovery:** Restart router, restore WireGuard config
- **Must not do:** Do not change NAT rules without backup

## Scenario 4: primary-candidate offline
- **What still works:** Home CP, all execution
- **Command node:** Home, Mac
- **How owner sends command:** Same as normal
- **Recovery:** Restart primary, restore from backup
- **Must not do:** Do not promote untested node

## Scenario 5: GitHub unavailable
- **What still works:** All execution, local code
- **Command node:** All
- **How owner sends command:** Same as normal
- **Recovery:** Use local repo, push later
- **Must not do:** Do not force push to recover

## Scenario 6: Control Plane split-brain
- **What still works:** Individual servers
- **Command node:** Authoritative CP (home:9101)
- **How owner sends command:** Kill duplicate CPs, verify single
- **Recovery:** Kill all CPs, start one clean instance
- **Must not do:** Do not run multiple CPs

## Scenario 7: agent-10 provider unreachable
- **What still works:** All other 20 servers
- **Command node:** Any
- **How owner sends command:** Same as normal
- **Recovery:** Check provider, restore network
- **Must not do:** Do not schedule tasks to agent-10

## Scenario 8: Owner uses another laptop
- **What still works:** Everything (after bootstrap)
- **Command node:** New laptop (after SSH key setup)
- **How owner sends command:** SSH with deploy key
- **Recovery:** Copy SSH key, verify access
- **Must not do:** Do not give new laptop root without approval
