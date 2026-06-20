# Rollback Plan

For every mutation task:

1. record base commit;
2. record result commit;
3. record changed files;
4. record migration/service changes, if any;
5. define rollback command before merge;
6. run smoke checks after rollback rehearsal where practical;
7. keep artifacts and logs immutable after review.

For production:

- deploy only from reviewed branch;
- keep previous artifact/service version;
- smoke test public endpoints;
- if smoke fails, restore previous artifact/service config;
- write an incident report under `.factory/logs/incidents/`.
