# Mimo runner main/qjns diagnosis

Date: 2026-06-29
Role: SRE Mimo runner main/qjns
Scope: diagnose Mimo runner on `main` and `qjns`; do not mutate Control Plane
queue state, do not run heavy LLM or FormulaLM workloads, do not change
`ops/agent_host.py`.

## Follow-up выполнен главным исполнителем

После диагностики `ops/agent_host.py` был исправлен и развернут на remote
hosts:

- `main` / `10.99.0.2`: `/usr/local/bin/kolibri-agent-host`;
- `qjns` / `10.99.0.4`: `/opt/kolibri/agent_host.py`;
- `qjns` / `10.99.0.4`: `/usr/local/bin/kolibri-agent-host`.

Перед заменой на каждом пути создан backup `*.bak-<UTC timestamp>`.
Проверка после копирования:

```text
python3 -m py_compile <remote-agent-host-path>
sha256: d9d6fbb397f13ece9b0448994fb42cfc98f99b9318bea8e0b06f19f237c94bbd
```

`kolibri-agent-host.service` перезапущен на `main` и `qjns`; оба сервиса после
перезапуска вернули `active`.

Новый runtime-контракт:

- auto-detect современного Mimo CLI: `mimo chat --message <prompt> --json
  --no-stream`;
- fallback на legacy Mimo CLI: `mimo run --format json --title <title>
  <prompt>`;
- fallback на Codex при пустом parseable response сохранен.

## Executive summary

`main` and `qjns` are not failing for the same reason.

`main` has a working `/usr/bin/mimo` on the systemd `PATH`, but Agent Host calls
the old command contract:

```text
mimo run --format json --title <title> <prompt>
```

Installed `mimo 0.2.1` does not support `run`. Its supported non-interactive
shape is:

```text
mimo chat --message <text> --json --no-stream
```

So `agent_host` receives no parseable response because the runner exits with
usage/help text instead of the JSONL text events that `parse_json_text_response`
expects.

`qjns` is a runtime/bootstrap blocker. It runs an older deployed Agent Host,
does not advertise `generic_implementation`, has no `git`, `node`, `npm`, or
`codex` in PATH, and its `/usr/local/bin/mimo` symlink points at the legacy
`/root/.mimocode/bin/mimo` binary whose `--version` timed out.

No LLM/model/FormulaLM execution was started during this pass. Only help,
version, dry-run, systemd, journal, and Control Plane read-only checks were
used.

## Read-only checks run

Local from this worktree:

```bash
curl -fsS --max-time 5 http://10.99.0.2:9101/health
curl -fsS --max-time 5 http://10.99.0.2:9101/v1/nodes
curl -fsS --max-time 5 'http://10.99.0.2:9101/v1/tasks?summary=1&compact=1'
python3 -m py_compile ops/agent_host.py
```

Result: local curl to Control Plane timed out from this workspace, while
`py_compile` passed.

Remote read-only checks:

```bash
ssh root@10.99.0.2 'systemctl show kolibri-agent-host.service -p MainPID -p ExecStart -p Environment -p User -p Group --no-pager'
ssh root@10.99.0.2 'tr "\0" "\n" </proc/$(systemctl show -p MainPID --value kolibri-agent-host.service)/environ | grep -E "^(PATH=|HOME=|USER=|KOLIBRI_|GIT_SSH_COMMAND=)"'
ssh root@10.99.0.2 'timeout 5s mimo --version; timeout 5s codex --version'
ssh root@10.99.0.2 'timeout 5s /usr/bin/mimo --help; timeout 5s /usr/bin/mimo chat --help'
ssh root@10.99.0.2 'timeout 5s /usr/bin/mimo --dry-run chat --message MIMO_DRY_RUN_SMOKE --json --no-stream'

ssh root@10.99.0.4 'systemctl show kolibri-agent-host.service -p MainPID -p ExecStart -p Environment -p User -p Group --no-pager'
ssh root@10.99.0.4 'tr "\0" "\n" </proc/$(systemctl show -p MainPID --value kolibri-agent-host.service)/environ | grep -E "^(PATH=|HOME=|USER=|KOLIBRI_|GIT_SSH_COMMAND=)"'
ssh root@10.99.0.4 'timeout 3s /usr/local/bin/mimo --version'
ssh root@10.99.0.4 'timeout 6s curl -fsS http://10.99.0.2:9101/health'
```

## main findings

Host identity:

```text
hostname: kolibri-main-api
kernel: Linux 6.8.0-35-generic
service: kolibri-agent-host.service active
node_id: main
agent_id: agent-host-main
```

Versions and binaries:

```text
PATH in agent_host process: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
mimo resolved by PATH: /usr/bin/mimo
mimo version: 0.2.1
codex resolved by PATH: /usr/bin/codex
codex version: codex-cli 0.142.2
python3: 3.12.3
git: 2.43.0
node: v20.20.2
npm: 10.8.2
```

There is also an old long-running process:

```text
/root/.mimocode/bin/mimo serve --hostname 0.0.0.0 --port 4096 --mdns --mdns-domain kolibri.local
```

That binary is not what `agent_host` resolves for command execution today,
because `/usr/bin/mimo` is earlier via the systemd PATH and `/usr/local/bin/mimo`
does not exist on `main`.

Deployed Agent Host:

```text
/usr/local/bin/kolibri-agent-host sha256:
d45030a4ce31083fa1e25faa3fe32022445e605c6033db25ab4040bc5314ba70
```

It contains `RunnerEmptyResponseError`, `runner_empty_response`, and the
Mimo-to-Codex fallback code for `generic_implementation`.

Systemd issues:

1. The unit is live-custom, not the repo standard env-file profile.
2. `GIT_SSH_COMMAND` is unquoted despite spaces. systemd logs:

```text
Invalid environment assignment, ignoring: -o
Invalid environment assignment, ignoring: -i
Invalid environment assignment, ignoring: /root/.ssh/kolibri_github_deploy_ed25519
```

The process environment therefore effectively has only:

```text
GIT_SSH_COMMAND=ssh
```

3. Advertised capabilities are:

```text
orchestrator,implementation,review,read_only_probe
```

They do not include the standard current runtime set:

```text
read_only_probe,generic_implementation,implementation,remote_implementation_runner_ready,review,image_generation,mesh_node,permission:*
```

Control Plane from `main`:

```text
GET http://10.99.0.2:9101/health -> status=ok, redis=PONG
```

Active node snapshot at 2026-06-29T11:41Z:

```text
main fresh=true health=online draining=false active_task=KOL-AUTOMATION-EXECUTION-POLICY-20260629
qjns fresh=true health=online draining=false active_task=null
fresh_canonical_generic_implementation_nodes=1
```

Observed Mimo failure:

```text
task_id: KOL-LOG-PROBE-MAIN-20260629-001
lease_owner: main:agent-host-main
runner: mimo
error_type: runtime_error
error: command failed with rc=1: /usr/bin/mimo run --format json --title factory-KOL-LOG-PROBE-MAIN-20260629-001 <prompt>
```

Concise stderr evidence:

```text
Unknown command: mimo run ...
Run mimo --help to view available commands.
```

`/usr/bin/mimo --help` and `/usr/bin/mimo chat --help` show that the installed
CLI supports `chat`, not `run`. A no-LLM dry-run works:

```bash
/usr/bin/mimo --dry-run chat --message MIMO_DRY_RUN_SMOKE --json --no-stream
```

It returns a JSON request with `model=mimo-v2.5-pro`, `stream=false`, and
`response_format={"type":"json_object"}`.

## qjns findings

Host identity:

```text
hostname: kolibri-tools-executor
service: kolibri-agent-host.service active
node_id: qjns
agent_id: agent-host-qjns
```

Systemd command:

```text
/usr/bin/python3 /opt/kolibri/agent_host.py \
  --control-url http://10.99.0.2:9101 \
  --control-urls http://10.99.0.2:9101,http://10.99.0.10:9101,http://10.99.0.1:9101 \
  --node-id qjns \
  --agent-id agent-host-qjns \
  --capabilities read_only_probe,implementation,review,qa,agent-host \
  --work-root /var/lib/kolibri-agent/worktrees \
  --artifact-root /var/lib/kolibri-agent/artifacts \
  --heartbeat-interval 10 \
  --lease-refresh 5 \
  --max-inflight 1
```

Runtime environment:

```text
PATH in process: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
KOLIBRI_FILE_ROOTS=root=/:ro
```

Missing tools:

```text
git: not found
node: not found
npm: not found
codex: not found
```

Mimo path:

```text
/usr/local/bin/mimo -> /root/.mimocode/bin/mimo
/root/.mimocode/bin/mimo: ELF 64-bit binary
timeout 3s /usr/local/bin/mimo --version -> rc=124
```

Deployed Agent Host:

```text
/opt/kolibri/agent_host.py sha256:
09e2fcbb1fcc97a548666e79ac29bc10531d3e7d640492fd8f6cfb26076ed143
```

This deployed file does not contain the current `RunnerEmptyResponseError`,
`runner_empty_response`, or Mimo-to-Codex fallback strings. It is an older
runtime.

Control Plane reachability from `qjns`:

```text
GET http://10.99.0.2:9101/health -> status=ok, redis=PONG
```

Journal before the current steady process showed repeated register timeouts and
systemd restarts around 10:27-10:41 UTC. The current node is fresh, but it is
not implementation-ready because the runner/toolchain is incomplete.

## Why Agent Host gets empty or bad response

There are three separate response failure modes:

1. `main` current Mimo CLI mismatch:
   `agent_host` calls `mimo run --format json --title ...`; installed Mimo
   expects `mimo chat --message ... --json --no-stream`. The command exits
   `rc=1` with help text, so no JSONL assistant text is available.
2. Older runtimes classify empty Mimo output as generic `runtime_error`.
   Current repo code has `RunnerEmptyResponseError`, but older deployed nodes
   like `qjns` do not.
3. Even after switching to `mimo chat --json --no-stream`, Agent Host still
   expects Codex-like JSONL text events. A compatibility adapter or parser
   change must convert Mimo JSON response into one of the accepted shapes:
   `part.text`, `msg.message`, top-level `message/text/content`, or
   `item.text`.

Because `ops/agent_host.py` is out of scope for this pass, the safe fix is a
runtime/path compatibility plan plus smoke commands. The code-level fix should
be done in a separate Agent Host-owned change.

## Safe fix proposal

### main

Do not restart while `main` owns an active task. Wait for active task completion
or explicitly drain/coordinate first.

Recommended low-risk order:

1. Fix `GIT_SSH_COMMAND` quoting in a systemd drop-in or regenerated service:

```ini
[Service]
Environment="GIT_SSH_COMMAND=ssh -i /root/.ssh/kolibri_github_deploy_ed25519 -o BatchMode=yes -o IdentitiesOnly=yes -o HostName=ssh.github.com -o Port=443 -o StrictHostKeyChecking=accept-new"
```

2. Standardize advertised capabilities in the service command or bootstrap
   profile:

```text
read_only_probe,generic_implementation,implementation,remote_implementation_runner_ready,review,image_generation,mesh_node,permission:*
```

Because the live unit passes `--capabilities` in `ExecStart`, setting only
`KOLIBRI_AGENT_CAPABILITIES` is not enough unless `ExecStart` is also
standardized.

3. For Mimo specifically, use one of these two options:

Preferred code fix, separate ownership:

```text
Teach Agent Host to call:
  mimo chat --message <prompt> --json --no-stream
and parse Mimo JSON into response text.
```

Temporary path shim, requires explicit operator approval:

```text
Install /usr/local/bin/mimo ahead of /usr/bin in PATH.
The shim should translate:
  mimo run --format json --title <title> <prompt>
to:
  /usr/bin/mimo chat --message <prompt> --json --no-stream
and emit Codex-like JSONL:
  {"msg":{"type":"agent_message","message":"..."}}
```

Do not deploy the shim until it passes the no-LLM parse smoke below.

### qjns

Treat `qjns` as not ready for Mimo implementation tasks until bootstrap is
repaired.

Recommended low-risk order:

1. Keep it out of implementation/Mimo work until fixed. If it starts receiving
   such leases, drain it first via Control Plane with owner approval.
2. Replace the old runtime with the current standard Agent Host deployment.
3. Install or restore required tooling: `git`, `node`/`npm` if the selected Mimo
   CLI needs Node, and `codex` only if Codex fallback is desired.
4. Replace the hanging `/usr/local/bin/mimo -> /root/.mimocode/bin/mimo` path
   with a bounded, version-reporting Mimo CLI or a tested compatibility shim.
5. Advertise standard capabilities only after the no-LLM smoke passes.

## No-LLM smoke commands

Run on each node before any real `mimo chat`:

```bash
set -euo pipefail

echo "service"
systemctl is-active kolibri-agent-host.service
systemctl show kolibri-agent-host.service \
  -p MainPID -p ExecStart -p Environment -p EnvironmentFiles -p User -p Group \
  --no-pager

echo "process env"
pid="$(systemctl show -p MainPID --value kolibri-agent-host.service)"
tr '\0' '\n' <"/proc/${pid}/environ" \
  | grep -E '^(PATH=|HOME=|USER=|KOLIBRI_|GIT_SSH_COMMAND=)' \
  | grep -Ev 'TOKEN|KEY|SECRET|PASSWORD|AUTH' || true

echo "runner versions"
command -v mimo
timeout 5s mimo --version
timeout 5s mimo --help >/tmp/mimo-help.txt
grep -E 'chat|--json|--no-stream|--dry-run' /tmp/mimo-help.txt

echo "dry-run, no model call"
timeout 5s mimo --dry-run chat --message MIMO_DRY_RUN_SMOKE --json --no-stream \
  | python3 -m json.tool >/tmp/mimo-dry-run.json
grep -q '"stream": false' /tmp/mimo-dry-run.json
grep -q '"json_object"' /tmp/mimo-dry-run.json
```

Parser compatibility smoke for a proposed shim:

```bash
tmp="$(mktemp)"
printf '%s\n' '{"msg":{"type":"agent_message","message":"MIMO_SHIM_OK"}}' >"${tmp}"
python3 - <<PY
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("agent_host", "/usr/local/bin/kolibri-agent-host")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
assert module.AgentHost.parse_json_text_response(Path("${tmp}")) == "MIMO_SHIM_OK"
print("parse smoke ok")
PY
rm -f "${tmp}"
```

Control Plane read-only smoke:

```bash
curl -fsS http://10.99.0.2:9101/health
curl -fsS http://10.99.0.2:9101/v1/nodes \
  | python3 -m json.tool \
  | grep -E '"node_id": "(main|qjns)"|"fresh"|"capabilities"|"active_task"'
```

Forbidden in this pass:

```text
mimo chat without --dry-run
mimo run
FormulaLM benchmark
Qwen/Ollama/vLLM/llama.cpp model workload
Agent Host restart during an active lease
Control Plane queue surgery
```

## Current status

`main`: Mimo binary is reachable and dry-run works, but the Agent Host Mimo
command contract is wrong for installed Mimo 0.2.1. Also fix systemd quoting and
capability drift before relying on it for broader runtime work.

`qjns`: not Mimo-ready. It needs runtime bootstrap/toolchain repair before any
implementation or Mimo runner task. The hanging legacy Mimo binary is the first
thing to remove or replace.
