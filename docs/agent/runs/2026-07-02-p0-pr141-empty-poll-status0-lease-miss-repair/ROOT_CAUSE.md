# ROOT CAUSE

The PR #141 runtime canary failed after the JSON/logging optimization because the remaining pressure was below response formatting:

- warmed empty `/v1/tasks/lease` requests still waited behind the capped HTTP worker executor;
- replying before draining a complete POST can produce client-side reset/status `0`;
- persisted queued-task recovery could return `no_task` after a bounded random queued-index sample missed the compatible task.

The strict canary evidence was:

- stage100 empty `status0=49`;
- stage250 empty `status0=246`;
- stage500 `leased=498/500` and empty `status0=463`;
- stage1000 `leased=997/1000` and empty `status0=884`.

This repair adds a complete-request accept-loop empty-lease shortcut and strengthens persisted queued-index recovery so a bounded random window cannot hide a compatible queued task.
