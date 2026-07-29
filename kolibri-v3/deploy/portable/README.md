# Kolibri V3 portable production release

This package installs one isolated Kolibri V3 instance on a Linux host with
systemd. It never copies credentials into a release and does not modify another
Kolibri instance when a unique `KOLIBRI_INSTANCE`, install root, and ports are
used.

## Host requirements

- Linux with systemd, Bash, curl, tar, git, and `flock`
- Python 3 with `venv`
- Node.js 20 or newer and npm
- an existing non-root service account
- Codex CLI authenticated as that service account when the direct agent runtime
  is enabled
- a healthy MiMo runtime owned by this deployment when `KOLIBRI_REQUIRE_MIMO`
  is enabled
- optional Nginx and an existing TLS certificate

## Build an immutable source archive

Run this only from a clean committed V3 tree:

```bash
./deploy/portable/build-release.sh
```

Copy the resulting archive and its `.sha256` file to the target host, verify the
checksum, and extract it.

## Install

```bash
cp deploy/portable/config.env.example deploy/portable/config.env
# Edit the instance, service user, domain, paths, ports, and TLS certificate.
sudo ./deploy/portable/install.sh ./deploy/portable/config.env
```

To validate the host, agent credentials, MiMo, Nginx, and TLS without changing
the server:

```bash
sudo KOLIBRI_PREFLIGHT_ONLY=true \
  ./deploy/portable/install.sh ./deploy/portable/config.env
```

The installer builds and tests the release before activation, creates an atomic
`current` symlink, binds both application processes to loopback, installs
instance-specific systemd units, backs up the SQLite database, and rolls back
the services and reverse-proxy configuration if a health gate fails.

The persistent database and CSRF secret live below `KOLIBRI_INSTALL_ROOT/var`;
they are not stored inside a release.

## Pre-deployment smoke test

This performs a clean dependency install and production build, then starts the
standalone frontend and backend with a temporary database and temporary ports:

```bash
./deploy/portable/smoke-test.sh
```
