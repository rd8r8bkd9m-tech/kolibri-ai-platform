# Kolibri toolchain policy

`toolchains.json` is the sole version authority for builds, tests, releases and
the canonical 21-node fleet. It pins the newest supported stable release for
Python and Rust and the newest supported Node.js LTS release. Preview, beta,
nightly, EOL and unbounded `latest` versions are not release inputs.

An update is one atomic change: manifest, version files, CI, container bases,
lock files and runtime installer evidence. Downloads are accepted only from an
official project distribution and only after checksum or signature
verification. Home receives a side-by-side toolchain first; canary and the
full regression suite must pass before the same signed manifest is scheduled
across workers. Existing production binaries remain available for rollback.

Every release records build and runtime versions. `scripts/verify_toolchains.py`
blocks CI when the executable versions do not exactly match the manifest. The
fleet rollout additionally requires each node to report the same version set
and a fresh verifier-bound evidence hash; a heartbeat alone is insufficient.
