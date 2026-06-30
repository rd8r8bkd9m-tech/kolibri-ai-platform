# Kolibri Superfactory Roadmap

Date: 2026-07-01

This roadmap preserves the confirmed canvas order. Items after P0 runner
hardening are follow-up tasks and must not be implemented in the current P0
runner hardening branch.

## P0 Foundation

1. Harden Agent Host generic runner contract.
2. Create Superfactory documentation package.
3. Create GitHub always-current policy.
4. Inventory whole fleet.
5. Repair degraded nodes: `uiap` and `qjns` disk plus server GitHub auth.
6. Preserve dirty runtime diffs.

## P1 Coordination

7. Create skill registry and internet skill discovery pipeline.
8. Create agent team mesh.
9. Create anti-degradation system.
10. Rerun P0 integration contract audit.
11. Split PR #46.
12. Sync approved skills to servers.

## P2 Scale And Sovereignty

13. Design 100000 logical agents scheduler.
14. Design local LLM ring and sovereign model factory.
15. Add business/revenue engine with finance safety gates.
16. Add phone/video relay policy.

## P3 Interface And Autopilot

17. Add video-avatar meetings.
18. Define future `START_KOLIBRI_SUPERFACTORY_AUTOPILOT` command.

## Assembly Rule

The project is assembled by small GitHub PR layers:

- one purpose per branch;
- current PR description;
- included and excluded scope;
- tests or documented deferral;
- result artifacts;
- next recommended task.

## Current Gate

Do not proceed to fleet, skills, local models, business, or autopilot until the
runner contract is trusted enough to prevent false completion and hidden artifact
drift.
