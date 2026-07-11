# Kolibri Capability and Tool Gateway

Kolibri exposes one public model, `kolibri`. Codex/Mimo runner names and model
routes are internal execution provenance and are not entries in `/v1/models`.
Client-supplied `technical.provider_preferences` is accepted only for wire
compatibility and never changes routing.

## Runtime inventory

`GET /v1/capabilities` returns the probed skill, plugin, and tool inventory.
`GET /v1/tools` returns native tool records only. Installed skills never appear
there and cannot be submitted as response tools. Both endpoints use
the following truthful status vocabulary:

- `available`: the safe manifest metadata is valid and a required runner is
  executable;
- `degraded`: installation metadata exists, but a connector/runtime has not
  been verified;
- `unavailable`: the manifest reports unavailable, is invalid, or its runner
  is absent.

Only `available` native tool records may be included in `POST /v1/responses.tools`.
Unknown and ambiguous requests fail before execution. A stale native tool may
perform its safe availability probe; if it remains degraded or unavailable,
the response request fails with HTTP 422 before user work executes.

Skills remain in `/v1/capabilities`. A deterministic internal planner matches
request intent against installed skill frontmatter and adds selected `$skill`
names to the provider prompt. This does not create a native tool claim and does
not require the client to populate `tools`. A selected Codex skill also routes
away from providers that cannot load Codex skills.

The probe reads only:

- YAML frontmatter up to the closing delimiter in `SKILL.md`;
- `.codex-plugin/plugin.json` metadata;
- an explicitly configured `capabilities.json`, `tools.json`,
  `kolibri-capabilities.json`, or `kolibri-tools.json` runtime manifest.

It never reads skill bodies, `.env` files, MCP/app connector configuration,
cookies, tokens, or runner output as capability metadata. Configure safe roots
or exact manifest files with the path-separated
`KOLIBRI_CAPABILITY_MANIFEST_PATHS`. The default roots are
`$CODEX_HOME/skills` and `$CODEX_HOME/plugins/cache` (with `~/.codex` used when
`CODEX_HOME` is unset). Recursive default scans do not open generic
`tools.json`; a runtime JSON manifest must be configured as an exact path.

An installed plugin that declares MCP or app tools is reported as `degraded`
until an explicit runtime capability manifest confirms an available route.
This avoids presenting connector installation as proof of authentication or
connectivity.

Kolibri ships `backend/kolibri-tools.json` as the explicit native registry. It
currently defines:

- `tool:code_inspection`, mapped to Codex JSONL `command_execution` / `shell`
  events and constrained by the read-only runner sandbox;
- `tool:web_search`, implemented by Kolibri's controlled outbound HTTP gateway.

`tool:code_inspection` starts as `degraded`. `GET /v1/tools?refresh=true`, or
its first explicit owner request, runs a real read-only Codex request. It
becomes `available` only when the runner returns a matching successful JSONL
event, a non-empty answer, provider evidence, and a passed deterministic
verifier. The probe cache expires; absent, failed, rate-limited, or mismatched
probes return the tool to `degraded`, and requests then receive HTTP 422.

`tool:web_search` is available when the packaged controlled gateway is loaded;
it is never delegated to a runner shell. `web_search`, `web_search_preview`,
and `search_web` resolve to the same capability. The gateway accepts only a
bounded query, not an arbitrary URL. It calls a fixed HTTPS provider/path
allowlist with proxy inheritance disabled, verifies DNS and every redirect,
rejects non-public, loopback, private, link-local and metadata destinations,
caps redirects, timeout, response bytes, result count and provider context,
and falls through to the next allowlisted provider on a classified failure.
Citation URLs are normalized, tracking and sensitive query keys are removed,
and non-public citation hosts are discarded rather than fetched.

The search authorization is bound to the authenticated principal and a
response or task. Browser use additionally requires the short-lived public
session binding. Public sessions may request this one read-only capability and
cannot request shell/code inspection, functions, skills, durable projects, or
generic network access. The provider receives bounded, explicitly untrusted
search evidence; it receives no network capability. Public output contains
citations and content-bound tool hashes, never the session token or raw
authorization principal.

Example runtime tool metadata:

```json
{
  "tools": [
    {
      "id": "tool:web_search",
      "name": "web_search",
      "kind": "tool",
      "status": "available",
      "providers": ["gateway"],
      "aliases": ["web_search", "web_search_preview"]
    }
  ]
}
```

## Execution and evidence gate

When exactly one canonical Home Control Plane URL is configured, the first
transport is the API-only `factory` adapter. It discovers fresh, idle,
non-draining workers from `/v1/nodes`, requires a live `runner:mimo` or
`runner:codex` capability plus an `available` runner probe, submits an
idempotent read-only `/v1/tasks` envelope, and polls it under a bounded
deadline. It does not contain a server catalog and it never falls back to a
legacy Control Plane. Home/control-plane identities are excluded from provider
execution. A discovered binary is not enough: the worker must advertise
`kolibri.factory-provider.readonly.v1`, stdin prompt transport, a read-only
sandbox, a scoped worktree, and structured JSON/JSONL output. Legacy Agent
Hosts that place prompts in process arguments or grant danger-full-access are
ineligible and fail closed until the uniform runtime release replaces them.

The factory runner order remains Mimo Auto followed by Codex. Direct local
Mimo and capability-probed Codex are compatibility fallbacks, followed by
DeepSeek and the loopback-only local model. Codex probes GPT-5.6 Sol, GPT-5.6
Terra, GPT-5.6 Luna, GPT-5.5, GPT-5.4, then the specialized Codex Spark route.
Unsupported, outdated, quota-limited, or unavailable routes produce classified
internal attempts and fall through. These route identifiers remain under
response `technical` evidence; they are not public model choices.

A factory task is accepted as provider output only when task/result state is
`completed`, the result attempt matches the current fenced attempt, lease
node/agent and runner bindings match, output is non-empty, write-scope checks
are clean, and the answer hash passes the normal deterministic gateway
verifier. A stale heartbeat, queued task, terminal flag without a matching
result, or an unfenced late completion is rejected. Public provenance contains
an opaque node reference; physical topology stays in Home and `/control`.

Runner subprocesses receive an allowlisted environment. In particular,
`OPENAI_API_KEY`, `MIMO_API_KEY`, database URLs, service tokens, and arbitrary
service environment variables are not inherited. Codex and Mimo authenticate
through their configured runner homes; Kolibri does not call the OpenAI API
with a direct API key.

JSONL tool calls are retained only as sanitized provenance: safe tool/call
identifiers, status, event/input/output hashes, and redacted artifact
references. Raw commands, arguments, tool results, stderr, signed URL query
parameters, credentials, and file contents are not persisted under
`technical`.

`technical.tool_event_summary` contains only a raw-safe count, normalized event
types, normalized tool names, and status counts. `/v1/tools.runtime_probe`
returns the same safe event-name/type summary for the live availability probe;
it never returns raw JSONL, arguments, results, commands, or error bodies.

A response that requests tools is `completed` only when all of these checks
pass:

1. the assistant answer is non-empty;
2. zero-exit provider evidence is hash-bound to that answer;
3. every requested available tool has a successful content-bound execution
   record (a matching JSONL call for runner-native tools, or controlled gateway
   evidence for web search);
4. deterministic verifier evidence binds the answer, provider evidence,
   requested capability ids, and verified call ids.

Missing tool events, empty output, provider errors, or a failed verifier leave
the response failed. Provider acceptance, heartbeat, stderr, or unstructured
stdout alone never counts as completion.

Capability discovery and execution remain backend behavior behind the single
Home Control Plane authority. They do not introduce `main`, `primary`, local
loopback, or multi-authority Control Plane fallback.
