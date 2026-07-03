# Plan

- Re-materialize the Agent Host non-empty artifact contract in the proper repository worktree.
- Preserve the required behavior from the previous failed-but-useful main run: required artifacts must be present and non-empty, empty required artifacts must be reported separately, and canonical run artifacts must be mirrored into the artifact directory before manifest generation.
- Add or restore focused regressions for empty required artifacts and manifest-visible mirrored artifacts.
- Verify locally without restarting or deploying the live Agent Host.
- Commit, push a non-main branch, and open or update a draft PR.
