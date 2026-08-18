# Chat models: execution, selection, keys

## Catalog entry ≠ execution

A model visible in the catalog (`GET /v1/models/catalog`, rows in
`platform_models` / `user_models`) is **selectable, not executable**. The
selection only works if the direct runtime actually executes it:

- Selectable custom models use ids `platform:<id8>:<model>` / `user:<id8>:<model>`.
- `_custom_model_credentials` (`backend/app/direct_model_runtime.py:3989`)
  resolves the live OpenAI-compatible endpoint + decrypted key for such ids.
- `_custom_model_response` (`direct_model_runtime.py:4071`) streams an
  OpenAI-compatible chat completion via `MimoClientRuntime` with a system
  prompt built from instructions + optional `output_schema`.

Any new selectable model type needs an execution path plus tests, not just a
catalog row. The admin "connected" check only hits `GET /models` — it does not
prove the chat path works.

## Selection is frozen per run

Run acceptance freezes the model selection used by direct execution
(`test_run_acceptance_freezes_only_applicable_model_preferences`,
`test_acceptance_snapshot_is_the_selection_used_by_direct_execution`). Key
rules covered by `backend/tests/test_direct_model_selection.py`:

- Frozen selection must exist — invalid frozen Codex selection fails without
  fallback (`test_invalid_frozen_codex_selection_fails_without_fallback`).
- Missing execution context fails instead of silently using defaults
  (`test_missing_execution_context_fails_instead_of_using_defaults`).
- Execution-mode hints cannot override a frozen context
  (`test_execution_mode_hint_cannot_override_frozen_context`).
- Key-backed Gemini/DeepSeek profiles resolve only with an API key
  (`test_key_backed_gemini_profile_resolves_with_api_key`,
  `test_key_backed_deepseek_profile_resolves_with_api_key`).
- Developer access snapshot is locked, not broadened
  (`test_legacy_developer_access_snapshot_is_locked_not_broadened`).

## Where credentials live

- Tables: `platform_models` (admin-configured), `user_models` (user-supplied),
  `provider_connections` (provider enrollments); key material is stored
  encrypted and decrypted at execution time (`_decrypt_api_key` in
  `platform_models.py` / `user_models.py`).
- The dev backend reads keys only from `kolibri-v3/.env.local`
  (`scripts/dev-backend.sh` whitelists `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`,
  `OPENAI_API_KEY`, `MIMO_API_KEY`, `QWEN_SECRET_KEY`). A key inside a
  commented line (`# DEEPSEEK_API_KEY=...`) is **not** loaded.
- Never fabricate or guess keys; check `.env.local`, root `.env`, and the DB
  tables before concluding a key is missing. Turn missing-key errors into
  actionable messages.

## Billing interplay

Recurring billing gates platform entitlements; a model that is selectable but
whose tenant lacks a paid entitlement fails fail-closed at execution. See
`kolibri-billing` and `docs/SOURCE_OF_TRUTH.md` (tariffs/payment intents
rows).

## Related

- `backend/tests/test_direct_model_selection.py` — selection regression suite.
- `backend/app/model_catalog.py`, `backend/app/platform_models.py`,
  `backend/app/provider_connections.py` — catalog and credential storage.
