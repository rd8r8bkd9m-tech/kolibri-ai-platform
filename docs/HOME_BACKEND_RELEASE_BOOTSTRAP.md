# Home backend immutable-release drop-in bootstrap

This is the one-time, owner-operated bridge from the legacy Home backend unit
to the immutable `/opt/kolibri-ai/current` release layout. It does not publish
or switch a release. Normal releases remain signed and API-controlled.

## Safety boundary

- Home is resolved dynamically from the replicated mesh manifest.
- The default mode is a read-only remote plan; only `--apply` mutates Home.
- `/opt/kolibri-ai/current` must resolve to a direct child of
  `/opt/kolibri-ai/releases` and is never changed by this bootstrap.
- The current backend is imported with
  `/srv/kolibri/repo/.venv/bin/python` using a minimal non-secret environment.
- The current frontend `dist` directory must already exist.
- No environment file, provider credential, Telegram secret, Control Plane,
  mesh service or runner is read or changed.
- Apply installs only
  `/etc/systemd/system/kolibri-backend.service.d/10-release.conf` and restarts
  only `kolibri-backend.service`.

## Dry-run

```bash
scripts/bootstrap-home-backend-release.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json"
```

The sanitized JSON result must report:

- `status=planned`;
- `mutation=none`;
- `current_link=contained_direct_release_child`;
- `backend_import=verified_existing_venv`.

If another existing drop-in already makes the effective systemd
`WorkingDirectory` and `KOLIBRI_FRONTEND_DIST` point at `current`, plan reports
`status=already_configured`. Apply then performs no duplicate installation and
no restart, regardless of that existing drop-in's filename.

Dry-run streams the helper over SSH stdin. It creates no remote staging file,
backup, drop-in or lock.

## Apply

Apply is a protected owner action:

```bash
scripts/bootstrap-home-backend-release.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json" \
  --run-id "home-backend-release-$(date -u +%Y%m%dT%H%M%SZ)" \
  --apply
```

Before replacement, the helper stores root-only evidence under
`/var/backups/kolibri/backend-release-dropin/<run-id>/`:

- original drop-in bytes and metadata, or an explicit absent state;
- safe systemd unit metadata, excluding effective environment values;
- the unchanged current-link identity;
- apply or rollback status.

The helper atomically installs the repository drop-in, runs `daemon-reload`,
restarts the backend, and gates all of the following:

1. `kolibri-backend.service` is active;
2. effective `WorkingDirectory` is `/opt/kolibri-ai/current/backend`;
3. effective `KOLIBRI_FRONTEND_DIST` is
   `/opt/kolibri-ai/current/frontend/dist` without emitting the rest of the
   service environment;
4. the expected drop-in is effective;
5. `GET http://127.0.0.1:8001/api/health` succeeds with a JSON object; the
   gate retries bounded startup races for approximately 15 seconds;
6. the `current` symlink text and resolved target are unchanged.

If any post-install gate fails, the original drop-in or absent state is
restored atomically, systemd is reloaded, the previous backend configuration
is restarted and health-checked, and the result reports a sanitized rollback
status. The backup is retained for audit.

This source package does not itself assert a live rollout result. Dry-run,
apply and rollback evidence must be recorded separately by the owner-operated
release process.
