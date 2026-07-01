# Next

Required next action:

1. Provide or restore an approved node-scoped GitHub credential for `agent-host-qjns`, or approve an existing SSH deploy-key alias for the qjns Agent Host repo URL.
2. Re-run a qjns GitHub read-only clone probe after credential binding.
3. Reauthorize or policy-enable the qjns MIMO runner account/provider entitlement; current provider response is HTTP 403 `illegal_access`.
4. Re-run the harmless qjns MIMO probe after owner/provider reauth.

Do not run interactive `gh auth login`, `mimo auth login`, browser login, or device login on qjns without a separate owner-approved credential task.
