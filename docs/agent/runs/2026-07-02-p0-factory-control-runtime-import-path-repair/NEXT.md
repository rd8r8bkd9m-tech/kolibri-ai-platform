# Next

Next exact task:

`P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_PR_RELEASE_GATE_2026_07_02`

Objective:

Open and review the remote branch PR for the Factory Control runtime
import-path repair. If GitHub CI and review pass, merge to `main`, then run a
separate live deploy canary that first executes
`scripts/preflight-factory-control-runtime.sh` on the target control node.

Do not retry live deploy until this PR is merged and the deploy-preflight
passes on the actual target node/repo path.

