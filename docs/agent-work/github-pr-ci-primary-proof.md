# GitHub PR/CI primary proof

Дата проверки: 2026-06-29 14:38:21 MSK / 2026-06-29 11:38:21 UTC.

## Границы

- Merge/rebase/force-push в `main` не выполнялись.
- Выполнялись только read-only проверки и `git fetch origin main --prune`.
- Локальный `gh` отсутствует: `command -v gh` вернул пустой результат.
- `GITHUB_TOKEN` и `GH_TOKEN` в окружении отсутствуют.
- Неаутентифицированный GitHub REST для private repo вернул `404 Not Found`.
- REST-проверка ниже выполнена через существующий `git credential fill`; секреты не печатались.

## Репозиторий и ветка

- Repo: `rd8r8bkd9m-tech/kolibri-ai-platform`
- Origin: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git`
- Current branch: `codex/factory-autonomy-pwa-billing`
- Upstream: `origin/codex/factory-autonomy-pwa-billing`
- Local HEAD: `8222c179cc7df34caf60565c797ba8c55829dd78`
- Remote branch HEAD: `8222c179cc7df34caf60565c797ba8c55829dd78`
- `origin/main`: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Merge-base with `origin/main`: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Ahead of `origin/main`: 25 commits.

Commits ahead:

```text
8222c179cc7df34caf60565c797ba8c55829dd78 factory: speed up control plane task listing
aa3e551ff8564a334a9c126573387f3734a70743 factory: recover empty agent runner responses
801d28a2780905531eb96d3ed3a28c1e032886a2 factory: make telegram reports readable
a062eeaaba8dd8c01e361918ad9331f97edcb6d9 factory: alert on deliverable gate failures
5432ae6dfe69d909f0fec85414d77e963b186d44 factory: surface deliverable gate failures
d611ae2cf77fce383a2ee6602e9f33810d127724 factory: require deliverable evidence
fb7b4846057f7bf8f6f93bf0a070d7531dc13530 factory: format telegram status messages
ed52d968cce848efa2d5edb5c3ca3b4a55742b5f factory: surface watchdog rollup in control panel
522b7e27de3ba45b6ded02fb4b81ed665e99ba37 factory: roll up lease watchdog history
b41ea75d83390504baf01fcd450a4fc3a03eef11 factory: notify lease watchdog on action
23d431be5ee450ea73da9068c51ffdafe89f9a42 factory: schedule lease watchdog
15e43258e679c4cd1188bc7ee89fd7e88c34878f factory: sweep stuck task leases
bb6204b6681c182eb17e38a8b4bfc2dffe51493d factory: index task state queries
21cf952170bc718c13ab032fc7d20679fb924af7 factory: surface live cluster summary
cf1a6a2fc5a2c7cb722d3a109bf3dce822029329 factory: summarize canonical cluster nodes
4d20adddfa0bd84358d320134af04df420812424 factory: capture runner-created git results
e5a5b9413aa7bad87f0ba81759b45f8d5b051d2b factory: report all agent check to telegram
3b03e54279d8d6a128b7b1747486bc1f1ba67484 factory: record home runtime parity probes
972f38ebb4901039484ca9eb3c8e526e4cdcf3b5 factory: refresh watchdog after task submit
d3920329758f446b8fcadd4c0771a954eab0ee85 factory: add execution reports and machine tasks
4fd32d3d514f122dc04a4b4b0c7c28f775f0f4d5 factory: add self contained p0 verify task
a009c067fa33670b8aa2837befd0562d1e248805 factory: refresh watchdog and integration guidance
85b973cd60c5be2ddd7e0abc1d9c7bc102e92165 factory: land autonomy pwa billing rollout bundle
eadc04a07ca51812615f8b523c828d0fff1c136f factory: target eighty percent utilization
4ed9980542111228d4a9ce764dcdc461d548f1e8 factory: enable autonomous pwa and remote formulalm
```

## PR proof

Remote ref proof:

```text
git ls-remote origin 'refs/pull/*/head'
8222c179cc7df34caf60565c797ba8c55829dd78	refs/pull/46/head
```

REST proof via existing git credential:

- PR: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46`
- Number: `46`
- Title: `[codex] Factory autonomy, PWA billing, remote FormulaLM`
- State: `open`
- Draft: `true`
- Mergeable state: `clean`
- Head: `codex/factory-autonomy-pwa-billing` at `8222c179cc7df34caf60565c797ba8c55829dd78`
- Base: `main` at `6d0317c52a9694448ee2c352dc196ce7a27b9487`

## CI/check status

GitHub REST endpoints queried for HEAD `8222c179cc7df34caf60565c797ba8c55829dd78`:

- `GET /repos/rd8r8bkd9m-tech/kolibri-ai-platform/commits/{sha}/check-runs`
- `GET /repos/rd8r8bkd9m-tech/kolibri-ai-platform/commits/{sha}/check-suites`
- `GET /repos/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs?head_sha={sha}`
- `GET /repos/rd8r8bkd9m-tech/kolibri-ai-platform/commits/{sha}/status`

Result:

- Check runs: 2 total, both `completed/success`.
- Actions runs: 2 total, both `completed/success`.
- Legacy combined status: `pending` with `total_count: 0`; no legacy commit statuses exist, so this is not a failing CI signal.
- Check suites: 3 total. Two `github-actions` suites are `completed/success`; one `cursor` suite is `queued` with no check runs exposed by Actions.

Actions runs:

| Run ID | Workflow | Status | Conclusion | URL |
| --- | --- | --- | --- | --- |
| `28360693208` | `Kolibri CI` | `completed` | `success` | `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28360693208` |
| `28360688834` | `Kolibri CI` | `completed` | `success` | `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28360688834` |

Check-run jobs:

| Name | Status | Conclusion | URL |
| --- | --- | --- | --- |
| `ci` | `completed` | `success` | `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28360693208/job/84014347268` |
| `ci` | `completed` | `success` | `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28360688834/job/84014331895` |

## Local worktree note

At proof time the worktree already had unrelated modified/untracked files. This proof only added this document and did not revert or stage existing worktree changes.

## Plan to install `gh` on primary

Primary goal: make the primary node capable of normal PR/CI operations (`gh pr view`, `gh pr checks`, `gh run view --log-failed`) without relying on ad hoc REST scripts.

1. Confirm primary OS and package manager:

```bash
uname -a
cat /etc/os-release
command -v apt || command -v dnf || command -v yum || command -v zypper || command -v brew
```

2. For Debian/Ubuntu primary, install from the official GitHub CLI APT repository:

```bash
(type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)) \
  && sudo mkdir -p -m 755 /etc/apt/keyrings \
  && out=$(mktemp) && wget -nv -O"$out" https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  && cat "$out" | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
  && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && sudo mkdir -p -m 755 /etc/apt/sources.list.d \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && sudo apt update \
  && sudo apt install gh -y
```

Official source: `https://github.com/cli/cli/blob/trunk/docs/install_linux.md`.

3. Authenticate under the operator account, preferring the existing approved token flow:

```bash
gh auth login --hostname github.com --git-protocol https --scopes repo,workflow,project,read:org
gh auth status
```

4. Verify PR/CI read-only commands:

```bash
gh pr view 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform \
  --json number,title,state,isDraft,headRefName,headRefOid,baseRefName,url,statusCheckRollup

gh pr checks 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform --watch=false

gh run list --repo rd8r8bkd9m-tech/kolibri-ai-platform \
  --branch codex/factory-autonomy-pwa-billing --limit 10
```

5. Keep forbidden actions explicit unless separately approved:

- Do not run `gh pr merge`, `gh pr ready`, `gh pr close`, `gh run rerun`, `gh run cancel`, or `gh workflow run`.
- Do not publish raw logs containing secrets.
- Do not mutate Project/issue/PR metadata during the install proof.
