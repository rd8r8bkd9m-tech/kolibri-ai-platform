# Blocked Admin Actions

These actions require owner approval or upgraded/admin API capability.

## Branch Protection / Rulesets

Status: blocked by GitHub API response for private repo plan/visibility.

Recommended settings:

- require pull request before merge;
- require `Kolibri CI / ci`;
- block force pushes;
- block branch deletion for `main`;
- require review for high-risk areas;
- require CODEOWNERS review once owners are confirmed.

## Project Board Changes

Creating/reconfiguring `Kolibri Factory OS` changes GitHub workspace metadata. Owner should approve whether to create a new project or adapt the existing `Kolibri AI Platform: фабрика ИИ и продукт на миллиарды` project.

## Branch Archive/Delete

No branch deletion in this task. Stale branches must be classified first.

## Closing PRs/Issues

No PR or issue closure in this task. Conflicting/stale items should get comments and labels before closure.

## Write Workflows

Do not enable workflows that write labels/comments/issues/branches until least-privilege permissions and owner approval are recorded.
