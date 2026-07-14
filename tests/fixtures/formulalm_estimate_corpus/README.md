# FormulaLM estimate-corpus fixture

`approved-records.jsonl` is a historical fixture filename. The file contains
synthetic, non-production local-candidate records used only to verify declared
rights gates, deterministic normalization, duplicate removal,
project/source-group split isolation, and the Decimal boundary.

The fixture does **not** represent approval and does not claim that any real
corpus has been collected. Its hashes, consent IDs and prices are test-only
values. A passing test does not authorize FormulaLM training.
