# Estimate calculation contract v1

These schemas form the language-neutral boundary between Kolibri Product/Data
and deterministic estimate engines.

Contract rules:

- decimal values are non-negative base-10 strings, never JSON floats;
- only `source_backed` and `verified` prices participate in arithmetic;
- `preliminary` and `missing` prices cannot carry a committed `unitPrice`;
- release mode fails closed on incomplete price evidence;
- line totals and commercial adjustments use the declared rounding policy;
- output retains cost categories and source identifiers;
- the server remains the only authority allowed to persist a canonical result.

The Rust implementation lives in `packages/estimate-kernel-rs`. The Python
engine remains production-authoritative until both implementations pass the
same expanded golden corpus byte-for-byte.

