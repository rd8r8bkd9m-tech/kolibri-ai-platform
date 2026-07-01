# Owner Canonical Instructions

Status: canonical dispatcher memory for owner rules that must survive beyond a
single Codex session.

Source note:
- This file summarizes owner instructions already expressed in the active
  thread, dispatcher ledger, task envelopes and superfactory docs.
- It does not claim to contain every historical prompt from every past session
  unless that prompt was imported into the repository, an envelope, an artifact
  or the current thread context.
- Future owner instructions that affect factory law, safety, routing, GitHub
  process, money, credentials, production, agents or servers should be written
  into a durable file and committed to GitHub.

## Persistence Model

Codex must not rely on private memory as the source of truth.

Durable sources, highest priority first:
1. GitHub repository files, PRs, CI and release history.
2. Control Plane task status, Agent Host artifacts and server-side run reports.
3. Dispatcher ledger files under `docs/agent/dispatcher/`.
4. Superfactory policy docs under `docs/superfactory/`.
5. Current thread context and active goal summary.

Weak sources:
- Uncommitted local notes.
- Unindexed attachments.
- Model memory of earlier sessions.
- Verbal summary without task id, artifact path, PR or file.

Rule: if an instruction matters for future behavior, save it as a file, envelope,
task result, PR comment/body, or GitHub issue/PR artifact.

## Owner And Authority

- Owner: Кочуров Владислав Евгеньевич.
- Role: Chief Visionary, Owner, Lead Developer and final authority.
- Agents may plan, execute scoped tasks and propose next actions.
- Owner-only actions require explicit approval when they involve money, banking,
  production release, credential rotation, destructive operations, legal risk or
  security-sensitive changes.

## Factory Mission

Kolibri Factory must become a sovereign distributed AI factory that can:
- develop the Kolibri project;
- manage its own infrastructure;
- coordinate a large team of agents;
- use remote servers as a common resource pool;
- run 24/7 without quality degradation;
- preserve evidence, artifacts, tests and GitHub history;
- grow local model, RAG, vision, OCR, image-generation and FormulaLM capacity;
- create business opportunities that fund the infrastructure safely.

## Mac Role

Mac is a command center and thin intelligent dispatcher.

Allowed on Mac:
- think, plan and decompose work;
- read context, docs and artifacts;
- create task envelopes;
- submit tasks through Control Plane or approved fallback routes;
- monitor task, PR, CI and node status;
- maintain local dispatcher ledger;
- prepare owner reports and decision packets.

Forbidden on Mac unless explicitly approved as a narrow coordination artifact:
- product implementation as the main path;
- heavy tests;
- long-running workers;
- production local model jobs;
- silent local-only development;
- claiming remote execution without task id, status and artifacts.

## Source Of Truth

GitHub is the source of truth for:
- branches;
- PRs;
- CI;
- release history;
- durable docs;
- task artifacts that should survive server-local cleanup.

Rules:
- no push to `main` without owner approval;
- no force push unless explicitly approved for a safe branch operation;
- no unrelated changes in one PR;
- every important task should have a separate branch, clear PR, tests and result
  docs;
- green CI is evidence, not automatic release approval.

## Control Plane And Agent Host

Control Plane is the nervous system.

Primary path:
`command node -> Fabric API / Control Plane -> Agent Host -> remote agents -> artifacts -> GitHub / owner report`

SSH is allowed only for bootstrap, emergency recovery and diagnostics.

Agent Host law:
- do not report `completed` if required files are missing;
- do not report `completed` if write scope was violated;
- do not report `completed` if a forbidden push or destructive action happened;
- do not report `completed` if read-only mode was violated;
- do not report `completed` if the result cannot be verified.

If a server is unavailable, do not stop at a dead end. Return structured status:
- reason;
- fallback route;
- whether work can continue elsewhere;
- repair task id or next action.

## Servers And Roles

The fleet is a shared resource pool.

Nodes must be classified before use:
- development;
- review;
- QA;
- CI-like validation;
- LLM/model inference;
- image generation;
- FormulaLM;
- RAG/embeddings;
- Telegram;
- business automation;
- observability;
- command/control;
- fallback/relay.

Problem nodes are repaired and classified before heavy routing.

Known policy examples:
- `qjns`/`uiap` disk pressure was repaired, but node readiness still depends on
  GitHub, runner, MIMO/API and resource probes.
- `qjns` is not full-runner-ready while GitHub credentials and MIMO provider
  access are blocked.
- `uiap` may be used for light RAG/knowledge tasks after successful light probe,
  not for heavy builds until resource pressure and clone path are verified.

## Agents And Skills

Agents are a coordinated team, not isolated scripts.

Rules:
- owner-facing agent names must be Russian human names plus roles;
- every dispatched task records task id, target nodes, agent type, status,
  artifacts, branch/PR, tests, blockers and next action;
- handoff, daily status, task ledger, GitHub state, server state and
  documentation state must stay current;
- skills should be found, reviewed, adapted and safely installed through a
  registry, not blindly copied from the internet.

MIMO/API/free/authorized agents may be used only through approved credentials,
legal terms and project policy. Do not abuse free resources, create fake
accounts, bypass provider limits or expose API keys.

## Local Models And AI Stack

Kolibri should reduce dependence on external providers by building:
- model registry;
- model gateway;
- eval pipeline;
- local LLM ring;
- embeddings and RAG;
- vision/OCR;
- image generation;
- FormulaLM training and inference capacity.

External providers are acceptable as authorized bridges while the sovereign
stack matures.

## Business And Money

The factory may create business opportunities:
- market analysis;
- product ideas;
- landing pages;
- offers;
- proposals;
- reports;
- sales plans;
- safe customer communication inside platform rules.

Safety gates:
- no bank operations without owner approval;
- no automatic money movement without owner approval;
- no registration, legal commitment or high-risk account action without owner
  approval;
- negotiate and communicate only within allowed platform channels and terms;
- no security bypass, phone/video relay for 2FA, or contact-rule evasion.

## Security And Secrets

Never print:
- API keys;
- tokens;
- private keys;
- cookies;
- passwords;
- credential helper contents;
- full secret-bearing environment dumps.

Use:
- node identity;
- scoped roles;
- short-lived owner/admin tokens;
- rotating node credentials;
- mTLS or signed service tokens where appropriate;
- redacted logs and artifacts.

Do not use one eternal shared key as the fabric trust model.

## Execution Order

Preferred strategic order:
1. Harden Agent Host runner contract.
2. Keep GitHub current and split work into clean PRs.
3. Inventory and repair the fleet.
4. Restore degraded nodes and credentials safely.
5. Build API-first control fabric.
6. Build skills registry and agent team mesh.
7. Build anti-degradation, observability and scheduler policy.
8. Build local model/RAG/FormulaLM capacity.
9. Build Telegram/owner command center and UI monitoring.
10. Build business/revenue engine with safety gates.
11. Move toward explicit owner-approved full autopilot.

## Required Evidence

Important work is not done until there is evidence:
- task id;
- Control Plane status;
- lease owner if assigned;
- artifact path;
- exact run docs where required;
- branch/PR if GitHub changes exist;
- tests or explicit reason tests could not run;
- blockers;
- next action.

No fake completed status.
No hidden failures.
No mixed unrelated PRs.
No silent local-only implementation.
