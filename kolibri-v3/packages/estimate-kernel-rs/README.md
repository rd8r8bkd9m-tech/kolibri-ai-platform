# Kolibri estimate kernel

This crate is the future calculation boundary for Kolibri estimates. It is
deliberately independent from FastAPI, React, React Native, Tauri, AG-UI, A2A,
databases, network access, source retrieval, and document rendering.

## Current responsibility

Version `0.1.0` accepts normalized estimate rows and explicit commercial terms,
then deterministically calculates:

- line subtotals;
- totals by cost category;
- direct cost;
- overhead;
- profit;
- discount;
- tax;
- final total;
- completeness and price-source validation.

All decimal values cross the contract as strings. Money is rounded to two
decimal places with midpoint-away-from-zero semantics, matching
`decimal.ROUND_HALF_UP` for the non-negative estimate domain. Quantities are
normalized to six decimal places. Floating point input is not accepted.

The versioned JSON contracts and golden examples live in
`contracts/v1/estimates`.

## Authority boundary

The Product/Data backend remains authoritative. A browser, native app, Tauri
shell, WASM build, or agent may display a provisional calculation, but cannot:

- approve an estimate;
- create a canonical estimate version;
- issue an approved export;
- mark an estimate verified;
- override server provenance or release gates.

During migration, Python remains the production implementation and this crate
runs in shadow mode against the same normalized inputs. Production cutover is
allowed only after the shared golden corpus is byte-for-byte compatible and a
rollback flag exists.

## Commands

```bash
cargo fmt --manifest-path packages/estimate-kernel-rs/Cargo.toml --check
cargo clippy --manifest-path packages/estimate-kernel-rs/Cargo.toml \
  --all-targets -- -D warnings
cargo test --manifest-path packages/estimate-kernel-rs/Cargo.toml
```

The CLI reads one calculation request from standard input and emits one result:

```bash
cargo run --quiet \
  --manifest-path packages/estimate-kernel-rs/Cargo.toml \
  < contracts/v1/estimates/examples/valid-calculation-request.json
```

## Planned integration

1. Keep the JSON CLI as the first language-neutral conformance adapter.
2. Add a Product backend shadow runner with bounded time and no release
   authority.
3. Grow the golden corpus from verified production-like fixtures.
4. Add PyO3/maturin only after the contract stabilizes.
5. Cut over the server calculation behind a measured feature flag.
6. Consider WASM/native preview later; server recomputation remains mandatory.

