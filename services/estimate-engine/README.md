# Estimate engine

Isolated deterministic estimate arithmetic service. It does not source prices
and does not replace the evidence layer; fields such as `region` are preserved
in the canonical input and therefore affect its fingerprint.

## HTTP contract

- `GET /health` returns engine identity, rounding policy, and limits.
- `POST /calculate` accepts an estimate input and returns the calculated result
  plus canonical input/result SHA-256 fingerprints.
- `POST /fingerprint` calculates and returns only the two fingerprints.
- `POST /verify` accepts `{input, result, input_sha256?, result_sha256?}` and
  independently recalculates the expected result.

All decimal fields (`quantity`, `price`, `overhead_rate`, `vat_rate`, and every
calculated amount) are JSON strings. Input decimals use plain nonnegative
notation without signs, exponents, commas, or surrounding whitespace.

The engine normalizes input decimals before hashing. Canonical JSON uses UTF-8,
sorted object keys, no insignificant whitespace, and preserved array order.
`result_sha256` covers the `result` object, not the HTTP response envelope.

Arithmetic is backed by `BigInt`; there is no binary floating-point path.
Every line is rounded to two decimals with `ROUND_HALF_UP`, subtotal is the sum
of rounded lines, overhead is rounded from `subtotal * rate / 100`, VAT is
rounded from `(subtotal + overhead) * rate / 100`, and total is their exact sum.

