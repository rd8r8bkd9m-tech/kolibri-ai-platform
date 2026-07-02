# Local Model Ring Capacity Snapshot

Task: `P0_AUTOPILOT_EXTRA_44_LOCAL_MODEL_RING_CAPACITY_2026_07_02`
Generated: `2026-07-02T02:55:43Z`

## Source Evidence

- Prior fleet inventory saw `42` visible Control Plane cards and separated
  owner-facing nodes, mesh shadow cards and stale metadata cards.
- Fresh runner-capable model/agent candidates from the prior inventory:
  `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, constrained
  `mesh-9fts`, constrained `main`.
- Specialized non-general capacity:
  - `uiap`: light CPU-only RAG, embeddings and skills registry work.
  - `qjns`: online after disk repair, but GitHub/MIMO credentials are not safe
    for implementation or review.
- Stale or blocked owner-facing cards:
  `home`, `home-live`, `primary-candidate` require heartbeat freshness repair
  before counting as normal model-ring capacity.
- Control Plane local read probe from this worker did not return live node JSON:
  `127.0.0.1:8080` refused connection and `127.0.0.1:8000` returned `404` for
  `/v1/fabric/health` and `/v1/nodes`. This run therefore relies on checked-in
  Control Plane artifacts and repo contracts.

## Capacity Classification

| Pool | Counted now | Candidate nodes | Current capacity judgment | Blockers |
| --- | ---: | --- | --- | --- |
| MIMO/Codex remote agents | 4-5 constrained | `mesh-agent-01..03`, `mesh-9fts`, `main` | Usable for bounded AI-runner tasks; broad fanout still needs post-PR91 canary and auth classification | `main` low memory/auth risk; broad MIMO canary pending |
| Local LLM model serving | 0 proven | future: `mesh-agent-01..03`, `mesh-9fts`; after repair: `home`, `primary-candidate` | No Ollama/vLLM service is proven by current artifacts; only Agent Host `KOLIBRI_LOCAL_LLM_URL` client path exists | missing hardware/GPU inventory; no model registry; model routes are safe stubs |
| RAG/embeddings | 1 light | `uiap` | Suitable for light CPU embeddings/RAG only | low RAM; no broad GitHub push; no heavy models |
| Tool/executor support | 1 blocked | `qjns` | Useful for read-only diagnostics and credential repair probes | missing GitHub credential; MIMO provider access denied |
| Owner gateway/model orchestration | 0 counted now | `home`, `home-live`, `primary-candidate` after repair | Do not count until heartbeat freshness is repaired | stale cards/freshness ambiguity |

## Integration Tasks

| Integration | Current repo/control-plane status | Required task | Blocker |
| --- | --- | --- | --- |
| Ollama | Mentioned as future CPU/edge serving; no dedicated service artifact or `/v1/models` record found | Create `P0_LOCAL_MODEL_NODE_OLLAMA_DISCOVERY_2026_07_02`: on `mesh-agent-01`, inspect installed binaries/services, disk/RAM, candidate small models, and define non-secret `ollama` health/model contract | no hardware/service inventory; no license/model cache register |
| vLLM | Mentioned as future text-serving stack; no GPU inventory or running endpoint proven | Create `P0_LOCAL_MODEL_NODE_VLLM_GPU_INVENTORY_2026_07_02`: collect GPU/VRAM/driver/disk facts on model candidates and decide vLLM-eligible nodes | GPU/VRAM unknown; model downloads forbidden until license and disk gates |
| LiteLLM | Provider stack mentions LiteLLM, but Control Plane model catalog has only safe stub `mimo-auto` | Create `P0_MODEL_GATEWAY_LITELLM_CONTRACT_2026_07_02`: design a non-secret gateway contract mapping `/v1/responses`, `/v1/chat/completions`, `/v1/models` to local/MIMO/API providers | no model registry; provider auth must not leak; route policy incomplete |
| MIMO | First-class Agent Host runner exists; PR91 repaired output/auth classification; direct fanout still has node-specific blockers | Run `P0_PR91_POST_MERGE_MIMO_RUNNER_CANARY_2026_07_01`, then rerun direct MIMO fanout excluding `qjns` until credentials are repaired | canary pending; `main` auth risk; `qjns` provider denied |
| Kimi | Global provider map and PR report list Kimi integration PR #36; no current model-ring route evidence found in local artifacts | Create `P0_KIMI_PROVIDER_ROUTE_AND_POLICY_AUDIT_2026_07_02`: verify PR #36 status, provider adapter surface, data policy, and whether Kimi should route through LiteLLM or direct OpenAI-compatible adapter | PR status needs fresh GitHub/CI check; provider credentials must not be probed or printed |

## API/Contract Gaps

- `ops/factory_control.py` has `MODEL_CATALOG` with a safe-stub `mimo-auto`
  only; authenticated model-node routes are not enabled.
- `ops/agent_host.py` supports `run_local_llm_text_runner` through
  `KOLIBRI_LOCAL_LLM_URL`, `KOLIBRI_LOCAL_LLM_MODEL` and
  `KOLIBRI_LOCAL_LLM_TIMEOUT`, but current artifacts do not prove those
  variables are configured on any node.
- The requested future primary interface is `/v1/responses`; compatibility
  stays `/v1/chat/completions`; both need `/v1/models` records before local
  model capacity can be counted as available.
- The referenced `docs/superfactory/12_LOCAL_LLM_RING.md` does not exist yet;
  `docs/superfactory/Kolibri_All_Prompts.md` names it as a required future
  artifact.

## Blockers

1. No fresh live Control Plane node JSON was available from this worker's local
   read endpoints.
2. Local model ring has design intent but no proven Ollama/vLLM/LiteLLM runtime
   service in checked-in artifacts.
3. GPU/VRAM inventory is missing, so vLLM capacity cannot be counted.
4. Model license/register and disk budget are missing, so model downloads must
   remain blocked.
5. `qjns` is blocked for MIMO/GitHub by credential/provider access.
6. `main` is constrained by low memory and prior runner auth risk.
7. `home`, `home-live` and `primary-candidate` need heartbeat freshness repair
   before model-ring scheduling.
8. Broad MIMO fanout depends on the post-PR91 canary.

## Next Exact Task

`P0_LOCAL_MODEL_NODE_DISCOVERY_AND_GATEWAY_CONTRACT_2026_07_02`

Run on `mesh-agent-01` first, fallback `mesh-agent-02`, with docs-only plus
read-only probes. Required outputs:

- hardware table: CPU, RAM, disk, GPU/VRAM, Docker, Python;
- service table: Ollama, vLLM, LiteLLM, MIMO, local Agent Host LLM URL presence
  as configured/not configured without printing values;
- `/v1/models` draft registry entries for every discovered model/service;
- `/v1/responses` and `/v1/chat/completions` routing contract;
- license/download gate for any model;
- exact blockers and safe rollout order.

## Russian Owner Summary

Статус: полезная инвентаризация завершена на серверном worker `mesh-agent-44`
в worktree на узле `kolibri`. Локально на Mac продуктовый код не менялся.

Сейчас подтвержденной локальной LLM-ring емкости нет: есть готовность
контрактов и runner-путь в Agent Host, но нет доказанного Ollama/vLLM/LiteLLM
сервиса и нет заполненного `/v1/models`. Для MIMO есть рабочие узлы
`mesh-agent-01..03` и ограниченно `mesh-9fts`/`main`, но нужен post-PR91 canary.
`uiap` подходит только для легкого RAG/embeddings. `qjns` пока заблокирован
credentials/provider access. Следующая точная задача: запустить
`P0_LOCAL_MODEL_NODE_DISCOVERY_AND_GATEWAY_CONTRACT_2026_07_02` на
`mesh-agent-01`.

