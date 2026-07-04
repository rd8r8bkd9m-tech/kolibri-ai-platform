# Split Required

PRs that must not be merged as-is:

- PR #46: too broad. Split into frontend/PWA, billing, factory runtime, estimator determinism, and FormulaLM tracks.
- PR #89: split/sequence verifier/auth prerequisites, single receiver migration, and Telegram bot/Mini App layer.
- PR #81: separate source runtime fixes from live Telegram behavior and sequence behind #83/#91/#89.

Reason:

These PRs mix runtime, product, documentation, and operational behavior in ways that would make verification and rollback too weak for the Superfactory release train.
