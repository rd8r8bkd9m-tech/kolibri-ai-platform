# Actions

- Submitted the remote task through Control Plane.
- The task leased to `primary-candidate:agent-host-primary`.
- The task-specific repo directory was initially empty; the remote agent initialized an isolated checkout from `refs/pull/141/head`.
- Verified the checkout resolved to exact PR #141 head `93df2ca5f07d99ad49a7b9bbd33f959b97906e14`.
- Removed the raw accept-loop shortcut from `FactoryThreadingHTTPServer.process_request`.
- Removed the helper functions that parsed and responded to lease requests directly from the accept loop.
- Updated the regression test so warmed empty lease polls must still enter the worker executor and the removed shortcut helpers must not exist.
- Mac command node relayed only the server-authored code/test diff plus these exact run artifacts because the old runner wrote artifacts to the previous task path.

