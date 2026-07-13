# Kolibri AI OS V2.1 RC release notes

## Product

Kolibri V2.1 introduces a clean, single-conversation Shell. Estimates and documents appear contextually; unavailable capabilities remain hidden.

## API

The public API uses `/v1`, the model name `kolibri`, OpenAI-style bearer keys, durable Responses, Conversations/Projects, Chat Completions, Models, Realtime, estimates, artifacts, and factory evidence contracts.

## Data and execution

The local release candidate uses SQLite and content-addressed filesystem artifacts. Task completion requires a non-empty result, valid attempt/fence, required artifact bytes, SHA-256, and verifier binding.

## Status

Local single-server gates are green. Distributed Home/21-node, Rust authority, PostgreSQL/JetStream/CAS, signed rollout, and 24-hour soak remain release gates and are not claimed as completed.
