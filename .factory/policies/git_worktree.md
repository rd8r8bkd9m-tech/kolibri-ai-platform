# Git And Worktree Policy

- Never develop directly on `main` or `master`.
- Every worker task uses `factory/<task-id>-<slug>`.
- Use separate worktrees for parallel mutation.
- One task should produce small atomic commits and no unrelated changes.
- Do not force push without explicit approval.
- Do not run `git reset --hard` when unknown changes exist.
- Do not delete unfamiliar files.
- Before merge: base is current, tests pass, review passes, security checks pass,
  acceptance criteria are proven, rollback is defined, and artifacts are
  registered.
- Production merge or deploy needs human approval.
