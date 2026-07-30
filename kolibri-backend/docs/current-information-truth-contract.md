# Current information truth contract

Questions whose answer can change with wall-clock time do not use the plain
provider-only chat path. Examples include weather, exchange rates, traffic,
schedules, news, and prompts containing “сейчас”, “сегодня”, “актуальный” or
“последний”.

The backend first invokes the web-search tool and applies this fail-closed
contract:

- no usable `http(s)` evidence: `status=needs_tool`,
  `error_code=current_information_evidence_unavailable`, no current factual
  claim, and the model is not invoked;
- usable evidence: `status=source_backed`, deterministic rendering of source
  title/snippet only, plus `citation`, `url`, and UTC `retrieved_at` for every
  source;
- provider prose is never accepted as proof that web search ran;
- source names without a URL and observation timestamp are not evidence;
- private reasoning is not exposed.

This is intentionally conservative. A vertical-specific weather, finance, or
transport tool may later replace the generic search renderer, but it must
preserve the same source/date/citation and fail-closed properties.
