# Skill: Kolibri CI Doctor

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-ci-doctor` |
| version | `0.1.0` |
| scope | `server` |
| owner | CI Doctor |
| status | `registered` |

## Purpose

Diagnose CI failures, identify root causes, and propose targeted fixes.
Separate test failures from infrastructure issues and runner problems.

## Trigger

- CI pipeline reports failure
- Test suite regression detected
- Build timeout or infrastructure error
- Post-merge canary failure

## Inputs

- CI failure logs and status
- Test suite results
- Build environment info
- Recent code changes

## Outputs

- Root cause classification (test/infra/runner/auth)
- Fix recommendation with confidence level
- Affected files and line numbers
- Regression vs new failure determination

## Safety Constraints

- Never modify test files without understanding failure
- Never skip tests to make CI pass
- Never hide failures
- Read-only diagnosis preferred before proposing fixes

## Dependencies

- CI system access
- Test framework output
- Repository source code
