# Stale Branch And PR Policy

## Classification Before Action

Every stale branch or PR must be classified as:

- merged;
- superseded;
- artifact-only;
- needs split;
- needs rebase;
- blocked;
- unknown.

## Forbidden Without Approval

- deleting branches;
- closing PRs;
- force-pushing rewritten history;
- squashing unrelated histories;
- removing artifacts before preservation.

## Minimum Archive Record

Before archive/delete, record:

- branch name;
- head SHA;
- linked PR/issue/task;
- changed areas;
- artifact paths;
- reason for archive;
- owner approval reference.

## Immediate Candidates For Classification

- historical `agent/TG-*` branches;
- early `factory/*` proof branches;
- conflicting PRs #7, #8, #25, #27;
- stacked non-main PR chains.
