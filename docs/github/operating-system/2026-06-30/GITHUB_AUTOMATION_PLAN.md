# GitHub Automation Plan

## Proposed Automations

- scheduled GitHub curator workflow;
- stale branch/PR report workflow;
- PR size/risk labeler;
- CI summary comment;
- label sync script;
- project board sync;
- issue creation from Control Plane tasks;
- artifact link updater.

## Safety Rules

Any workflow that writes to repo/issues/PRs must:

- use least privilege;
- not expose secrets;
- not auto-close important work;
- not merge automatically;
- log actions;
- include dry-run mode;
- be disabled by default until owner approval.

## First Automation To Build

Read-only daily GitHub status report that posts an artifact or comment only after owner approval.

## Not Yet Allowed

- auto-merge;
- auto-close;
- branch deletion;
- branch protection modification;
- payment/billing actions.
