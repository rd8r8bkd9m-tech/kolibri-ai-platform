# Director Tick Protocol

`POST /v1/director/tick` returns the next read-only governing actions:

- read fleet status;
- read queue status;
- classify blockers;
- propose repair tasks;
- avoid broad execution until owner approval gates pass.

Current implementation is intentionally conservative and local-only.
