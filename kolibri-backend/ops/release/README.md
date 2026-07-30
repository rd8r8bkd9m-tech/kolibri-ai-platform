# kolibriai.ru r9 API cutover

`kolibri_domain_api_cutover.py` is the only supported operator path for the
Home-domain API switch from legacy ports `8001`/`18013` to the side-by-side r9
listener on `127.0.0.1:18014`. It intentionally leaves the live Vite frontend
on `127.0.0.1:15193`.

The tool never reads provider, Telegram, browser, or API credentials. Public
functional checks use the signed anonymous browser-session contract.

## 1. Read-only plan

Run on Home as root from the exact reviewed release artifact:

```bash
python3 kolibri_domain_api_cutover.py plan \
  > /var/tmp/kolibri-r9-cutover-plan.json
```

The plan must report:

- `status=ready`;
- current config SHA-256;
- r9 `active`, `NRestarts=0`, `ExecMainStatus=0`;
- direct `/api/health` status `ok`;
- current and rendered-candidate `nginx -t` passed;
- all candidate backend locations point to `18014`;
- the frontend location remains exactly `15193`.

## 2. Direct functional gate before switching the domain

```bash
python3 kolibri_domain_api_cutover.py check \
  --release-id <release-id>-preflight \
  --public-base-url http://127.0.0.1:18014 \
  --frontend-base-url http://127.0.0.1:15193 \
  > /var/tmp/kolibri-r9-functional-gate.json
```

This gate requires real evidence for:

- Vite HTML;
- backend health and JSON 404 route isolation;
- anonymous session bootstrap;
- project create/message/list/delete/restore/reload lifecycle;
- deterministic text response (`56+67 = 123`);
- current-information response with a completed web-search trace and direct
  source URL;
- image generation with downloaded raster bytes whose MIME, size and SHA-256
  match the artifact metadata.

Any missing image bytes, provider terminal error, generic fallback, history
failure, HTML API fallback, or source-less current answer blocks the switch.

## 3. Approved atomic apply

Use the exact `current_sha256` emitted by step 1. The approval identifier and
release identifier are metadata, not credentials.

```bash
python3 kolibri_domain_api_cutover.py apply \
  --release-id <release-id> \
  --owner-approval <approval-id> \
  --expected-current-sha256 <sha256-from-plan>
```

Apply performs, under an exclusive lock:

1. the complete preflight again;
2. a metadata-preserving, checksum-verified backup under
   `/var/lib/kolibri/release-backups/api-cutover/`;
3. one atomic config-file replacement;
4. `nginx -t` before reload;
5. `systemctl reload nginx` (no backend or frontend restart);
6. the same full functional gate through `https://kolibriai.ru`;
7. verification that r9 did not restart and that the active routes still match
   the approved candidate.

If config validation, reload, any functional scenario, or service stability
fails, the tool automatically restores the byte-for-byte previous config,
tests it, and reloads nginx.

## 4. Exact manual rollback

The successful apply output contains `backup_dir`. Rollback is:

```bash
python3 kolibri_domain_api_cutover.py rollback \
  --owner-approval <approval-id> \
  --backup-dir <backup_dir-from-apply>
```

Rollback refuses a modified backup, restores the manifest-bound SHA-256,
runs `nginx -t`, and reloads nginx. It does not restart Vite, r9, legacy
backends, the mesh, Amnezia, or any Control Plane service.

## Release gate

Production remains unchanged until all conditions below are true:

1. The source release is immutable and identified by commit/release digest.
2. `plan` passes against the still-current approved config SHA-256.
3. Direct `check` passes every scenario, including actual image bytes.
4. r9 is stable with zero restarts throughout the observation window.
5. Owner approval is bound to the candidate SHA-256 and release ID.
6. Public post-check passes after reload; otherwise automatic rollback is
   observed and verified.
7. The old backend processes are stopped only in a separate, later cleanup
   after the domain route has remained healthy; this cutover tool does not
   stop them.
