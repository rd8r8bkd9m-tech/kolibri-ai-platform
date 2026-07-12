# Runtime version policy

Status date: 2026-07-12.

Kolibri pins the newest stable, non-RC and non-nightly runtime releases in two
root files:

| Runtime | Canonical pin | Official evidence |
| --- | --- | --- |
| Node.js | `26.5.0` | `https://nodejs.org/dist/index.json`, release dated 2026-07-08 |
| npm | `11.17.0` | bundled with the official Node.js `26.5.0` release |
| Python | `3.14.6` | `https://www.python.org/ftp/python/3.14.6/`, release artifact dated 2026-06-10 |

GitHub Actions use `actions/setup-node@v6` and `actions/setup-python@v6`, the
current stable action majors verified from their official GitHub releases on
2026-07-12.

`.node-version` and `.python-version` are the only version authorities. CI and
the Home development bootstrap consume those files instead of carrying their
own major-version literals. `scripts/check_runtime_version_pins.py` rejects
divergent workflow pins, package engine drift and can verify the installed patch
versions.

Node.js 26 is the current stable release, not the older LTS line. A later stable
release is adopted through a tested commit and Home canary; production hosts are
never upgraded implicitly. The Home bootstrap validates these versions but does
not install them, restart services or mutate production.

The Python 3.14 transition is currently blocked by `pydantic==2.9.0`, which
pulls a PyO3 build that rejects Python 3.14. Dependency remediation and its full
regression suite are a separate bounded change. The runtime pin remains explicit
so CI cannot silently fall back to an older interpreter.
