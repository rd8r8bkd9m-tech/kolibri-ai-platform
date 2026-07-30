# Kolibri V3 Home CI

Home CI replaces billed GitHub-hosted execution while keeping GitHub as the
source registry. It never deploys or restarts production.

The isolated flow is:

1. an exact Git commit is pushed over the existing SSH alias to the dedicated
   bare repository;
2. a user `systemd.path` unit queues one clean clone;
3. Docker runs Node 24.18, Python 3.12 and Rust 1.85 gates from pinned images
   (including checksum-pinned `rustup`, `rustfmt` and `clippy`) without
   production environment files or host runtime mounts;
4. logs, verified archive, checksum and status remain under
   `~/.local/state/kolibri-v3-home-ci/runs`;
5. the disposable source clone is removed after the run.

Install once on Home from a trusted checkout:

```bash
kolibri-v3/deploy/home-ci/install.sh
```

Submit and inspect an exact commit from the developer workstation:

```bash
kolibri-v3/deploy/home-ci/submit.sh home HEAD
kolibri-v3/deploy/home-ci/status.sh home
```

The receiver accepts only fast-forward updates of `refs/heads/candidate`.
Production services, Nginx, databases and ports are outside the CI state root
and are never mounted into the test containers.
