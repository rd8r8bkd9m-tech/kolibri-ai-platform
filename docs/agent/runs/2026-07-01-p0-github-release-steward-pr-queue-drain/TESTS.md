# Tests

Remote reported checks:

```bash
hostname
date -u +%Y-%m-%dT%H:%M:%SZ
git status --short
git remote -v
git branch --show-current
gh auth status
curl -fsSL 'https://api.github.com/repos/rd8r8bkd9m-tech/kolibri-ai-platform/pulls?state=open&per_page=100'
git ls-remote origin 'refs/pull/*/head'
git ls-remote origin refs/heads/main
git diff --check
```

Useful results:

- `git diff --check` passed on the server-created report.
- Git remote refs were readable.
- Direct unauthenticated GitHub REST PR list was blocked with HTTP 404.
- `gh` was unavailable on the server.
- Available connector reads were not sufficient for guaranteed repository-wide PR enumeration.

Dispatcher validation:

- Canonical markdown artifacts were created locally from server evidence.
- No product code was changed on Mac.
