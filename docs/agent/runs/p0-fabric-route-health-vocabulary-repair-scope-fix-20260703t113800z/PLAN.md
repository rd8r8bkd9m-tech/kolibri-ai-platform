# Plan

- Keep the repair scoped to Fabric route health vocabulary, route API surface tests, and this run's required artifacts.
- Centralize routable health handling in the route helper so `/v1/fabric/route` accepts fresh affirmative node states without accepting stale or drained states.
- Verify focused Factory Control tests and Python compilation before publish.
