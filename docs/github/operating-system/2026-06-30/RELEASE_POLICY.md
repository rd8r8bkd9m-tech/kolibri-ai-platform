# Release Policy

## Release Inputs

A release can only be cut from `main` after:

- CI green;
- release notes drafted;
- migrations and rollback documented;
- known blockers listed;
- owner approval recorded;
- production secrets not touched or safely rotated.

## Versioning

Use date-based prerelease tags until product semantics stabilize:

- `vYYYY.MM.DD-rc.N`
- `vYYYY.MM.DD`

## Release Notes

Each release note must include:

- summary;
- included PRs;
- excluded work;
- test evidence;
- deployment notes;
- rollback plan;
- known risks.

## Not A Release

Agent task artifacts, docs-only governance PRs and draft PRs are not releases.
