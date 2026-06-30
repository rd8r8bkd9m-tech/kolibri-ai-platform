# CI / GitHub Report

- Remote: `git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git`.
- Read refs: success via `git ls-remote --heads origin`.
- Mirror clone: success via resolved remote URL.
- Branch count from mirror: 93.
- CI config present: `.github/workflows/ci.yml`.
- GitHub Actions/PR API was not queried to avoid requiring or printing auth/env material in this read-only digest task.

## Failure classification

- No GitHub auth/network failure observed for refs.
- First clone failure was command-form/local invocation error: `origin` was passed where a clone URL was required.
- Local refs fallback available and inspected.

