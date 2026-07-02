# Verification

Commands run:

```sh
pwd && git status --short --branch
git remote -v
gh auth status
curl -fsS 'https://api.github.com/repos/rd8r8bkd9m-tech/kolibri-ai-platform/pulls?state=open&per_page=50'
git ls-remote origin 'refs/pull/*/head'
git ls-remote origin 'refs/pull/*/merge'
git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*/head' '+refs/pull/*/merge:refs/remotes/origin/pr/*/merge'
git log --oneline --decorate --max-count=20 origin/main
git for-each-ref --format='%(refname:short)' refs/remotes/origin/pr/*/head
git diff --name-status --find-renames origin/main...origin/pr/<n>/head
git diff --shortstat origin/main...origin/pr/<n>/head
date -u +%Y-%m-%dT%H:%M:%SZ
```

Connector checks:
- `get_pr_info` for PR #90, #93, #94, #87, #86, #84, #81, #61, #60, #38, #37, and #36.
- `get_commit_combined_status` for PR #90 and #93 heads returned no legacy status contexts.

Results:
- Worktree started clean.
- `gh` CLI is not installed.
- Unauthenticated REST is blocked for this private repo.
- Git over SSH and GitHub connector access succeeded.
- At least 10 open PRs were classified with exact state, draft, mergeability, base, and size.
- No product test suite was run because this task was queue triage, not code modification.
