# Lead Agent Access Policy

Project: KolibriAI Platform
Workspace: Calibri V1 transition branch
Date: 2026-07-05

This branch is a FastAPI/React/Fabric/Superfactory workspace. It is not the Rust foundation worktree. Treat it as an active product/runtime branch that must be aligned with Calibri V1 policy without destructive cleanup.

## Allowed Without Extra Approval

- Read and write project files in this repository and branch.
- Create or update source-of-truth, release, onboarding, and GitHub presentation docs.
- Run local build, lint, typecheck, compile, and test commands.
- Inspect local non-secret logs and generated artifacts when needed for diagnostics.
- Inspect bootstrap/deploy scripts without executing live mutations.
- Run non-destructive diagnostics against known project servers only when needed to align source of truth.

## Protected Actions

Return `USER_APPROVAL_REQUIRED` before any of these:

- destructive bootstrap or production deploy;
- DNS or REG.RU changes;
- firewall, public port, server reinstall, reboot, or production service restart;
- deleting databases, volumes, artifacts, logs, or branches;
- force push, history rewrite, branch deletion, worktree deletion;
- secret rotation or credential changes.

## Always Forbidden

- Print, log, commit, or copy raw secrets.
- Store passwords, tokens, cookies, SMS codes, 2FA codes, or private keys.
- Bypass 2FA/CAPTCHA.
- Give worker agents SSH or direct server credentials.
- Enable direct UI/LLM shell without approval, policy, and task binding.

## Worker Agent Rule

Worker agents must operate through Fabric/Control Plane API contracts. SSH is for owner/lead-agent diagnostics, bootstrap, and emergency recovery only.
