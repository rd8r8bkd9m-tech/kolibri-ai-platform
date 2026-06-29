# Agent1000 remote cluster manifest

Дата: 2026-06-29  
Роль: `agent1000_manifest_executor`  
Статус: machine-readable манифест создан; удаленные задачи этим документом не запускаются

## Назначение

Этот документ описывает целевой remote-only кластер на 1000 агентов для Kolibri
AI Platform. Машинный источник правды находится в
`ops/agent1000_manifest.json`.

Цель не в том, чтобы поднять 1000 процессов на Mac. Mac остается поверхностью
управления, чтения, редактирования и подготовки manifest/envelope файлов. Вся
вычислительная работа, тяжелые сборки, QA и FormulaLM/model workloads должны
идти только через удаленные Linux factory nodes, Control Plane leases и
node-local artifacts.

## Инварианты

- Все work tasks входят через `POST /v1/tasks` или
  `ops/kolibri-dispatch submit --file <envelope.json>`.
- Workers регистрируются через `/v1/nodes/register` и heartbeat через
  `/v1/nodes/<node_id>/heartbeat`.
- Lease обязателен: remote worker берет задачу через `/v1/tasks/lease`, работает
  в node-local worktree/artifacts и возвращает manifest reference.
- Control Plane хранит состояние, leases и ссылки на результаты; он не должен
  читать node-local файлы как общий writable root disk.
- SSH, ad hoc remote execution и legacy dispatcher compatibility mode не
  являются путем масштабирования Agent1000.
- FormulaLM/Qwen/model benchmark запрещено запускать на Darwin или owner Mac.
  Darwin preflight должен завершаться blocker artifact без запуска workload.
- Raw logs и artifacts публикуются только после redaction secrets/client data.

## Machine Manifest Summary

| Поле | Значение |
| --- | --- |
| Manifest | `ops/agent1000_manifest.json` |
| Version | `2026-06-29.agent1000.remote-cluster.v1` |
| `target_agents` | `1000` |
| `remote_only` | `true` |
| Roles | `24` |
| MIMO pool | `40` agents |
| Codex pool | `300` agents |
| FormulaLM pool | `35` agents |
| Main safety rule | no Mac execution for model work |

## Capacity Batches

| Batch | Agents | Purpose | Exit gate |
| --- | ---: | --- | --- |
| `batch_0_contract` | 25 | schema, lease, artifact, status contract validation | all role cards render and no remote work is submitted |
| `batch_1_probe` | 100 | remote read-only probes and runner readiness | probe artifacts exist for every selected node |
| `batch_2_functional` | 250 | implementation, review, docs, QA, orchestration lanes | queue/dead-letter rates remain within SRE thresholds |
| `batch_3_heavy_remote` | 500 | remote Linux build, QA, FormulaLM preflight capacity | no workload executes on Darwin or owner Mac |
| `batch_4_full_cluster` | 1000 | full remote cluster with reserve capacity and supervision | 1000 remote agents accounted for by role, pool, node class, and artifacts |

Scale-up is sequential. A failed gate pauses the next batch and routes ownership
to `factory_sre` plus the relevant role lead. There is no automatic jump from a
contract manifest to 1000 live agents.

## Pools

### MIMO

`mimo` contains 40 agents under `mimo_meta_orchestrator`.

Responsibilities:

- split owner intent into task envelopes;
- watch capacity batches;
- route blockers to owner-facing channels;
- coordinate cross-role artifact handoff.

Constraints:

- does not execute model workloads locally;
- does not bypass Control Plane leases.

### Codex

`codex` contains 300 agents:

- `codex_implementation_engineer`: 200;
- `codex_reviewer`: 100.

Responsibilities:

- repository implementation;
- tests and contract checks;
- code review;
- documentation patches.

Constraints:

- uses remote node-local worktrees for leased work;
- reports artifacts through manifest references.

### FormulaLM

`formulalm` contains 35 agents under `formulalm_remote_researcher`.

Responsibilities:

- remote-only benchmark design;
- preflight validation;
- deterministic estimate metrics.

Constraints:

- `platform.system == Darwin` blocks execution;
- model runtime never starts on owner Mac.

## Role Allocation

| Role | Agents | Pool |
| --- | ---: | --- |
| `mimo_meta_orchestrator` | 40 | `mimo` |
| `codex_implementation_engineer` | 200 | `codex` |
| `codex_reviewer` | 100 | `codex` |
| `qa_e2e_runner` | 70 | `quality` |
| `factory_sre` | 55 | `sre` |
| `control_plane_api_engineer` | 40 | `platform` |
| `agent_host_runtime_engineer` | 45 | `platform` |
| `mesh_bridge_operator` | 30 | `mesh` |
| `frontend_spa_engineer` | 65 | `product` |
| `mobile_pwa_gomesh_integrator` | 35 | `product` |
| `billing_tbank_engineer` | 25 | `commerce` |
| `docs_steward` | 35 | `docs` |
| `estimate_methodologist` | 45 | `domain` |
| `formulalm_remote_researcher` | 35 | `formulalm` |
| `data_eval_engineer` | 25 | `data` |
| `security_reviewer` | 25 | `security` |
| `product_designer` | 35 | `design` |
| `living_bird_motion_director` | 20 | `design` |
| `investor_sales_operator` | 20 | `business` |
| `github_project_operator` | 15 | `ops` |
| `release_manager` | 15 | `release` |
| `observability_engineer` | 10 | `sre` |
| `capacity_planner` | 10 | `sre` |
| `artifact_curator` | 5 | `docs` |

Total: 1000 agents.

## Node Classes

| Node class | Agents per node | Purpose | Model work |
| --- | ---: | --- | --- |
| `control` | 0 | Control Plane, owner status, orchestration, read-only routing | No |
| `standard_linux_worker` | 20 | implementation, review, docs, product QA, medium builds | No |
| `large_linux_worker` | 100 | heavy builds, E2E QA, controlled FormulaLM candidates | Yes, only after preflight |

Large Linux worker preflight must include:

- `platform.system != Darwin`;
- fresh heartbeat;
- `draining=false`;
- artifact directory writable;
- runtime version recorded;
- no active P0 incident on Control Plane or Agent Host.

## Scheduling Policy

- Batch order:
  `batch_0_contract -> batch_1_probe -> batch_2_functional -> batch_3_heavy_remote -> batch_4_full_cluster`.
- Capability match is required before lease.
- Fresh heartbeat is required before work assignment.
- Draining nodes are not eligible for new work.
- Dead-letter nodes are not eligible until investigated.
- Duplicate task ids are rejected.
- FormulaLM heavy runs wait until release QA pressure is clear.

## Blocker Policy

- If Control Plane health is not `ok`, stop at the current batch and publish a
  P0 blocker.
- If a selected node is stale or draining, exclude it until a read-only probe
  passes.
- If `platform.system` is Darwin for model or FormulaLM work, write a blocker
  artifact and exit without running the workload.
- If artifact manifest publishing fails, do not mark the task complete.
- If `dead_letter` grows during a batch, pause scale-up and route to
  `factory_sre`.

## Verification Commands

```bash
python3 -m json.tool ops/agent1000_manifest.json >/dev/null
python3 - <<'PY'
import json
d=json.load(open('ops/agent1000_manifest.json'))
assert d.get('target_agents')==1000
assert d.get('remote_only') is True
assert 'roles' in d and len(d['roles'])>=20
PY
git diff --check -- ops/agent1000_manifest.json docs/agent-work/agent1000-remote-cluster-manifest.md
```

Эти проверки валидируют contract artifact. Они не запускают удаленные агенты,
не стартуют FormulaLM/model workloads и не выполняют SSH.
