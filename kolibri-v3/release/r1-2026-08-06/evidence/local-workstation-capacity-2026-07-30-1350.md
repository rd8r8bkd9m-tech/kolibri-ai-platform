# Local workstation capacity recovery

Captured: 2026-07-30 13:50 MSK  
Host class: macOS development workstation, 8 GiB physical memory

## Result

| Check | Before | After |
|---|---:|---:|
| System volume available | 25 GiB | 48 GiB |
| System volume utilization | 90% | 80% |
| System memory free | 43% | 43% |
| Swap used | 0 MiB | 0 MiB |

The incident was disk-pressure plus transient CPU pressure after reboot, not
an active swap or out-of-memory condition.

## Reclaimed data

- all reproducible `.next` trees below the local Codex workspace
  (approximately 7 GiB);
- inactive `node_modules` trees outside the canonical V3 web and Expo apps;
- npm, Yandex, node-gyp, pip, Homebrew, uv, Node and giget caches;
- already-deleted V3 copies and ChatGPT Atlas that were present in Trash.

The selected Trash entries were permanently removed. Everything else in this
list is reproducible from lockfiles or normal tool operation.

## Deliberately preserved

- the canonical `kolibri-v3` source and Git object database;
- `kolibri-v3/node_modules` and
  `apps/kolibri-mobile/node_modules`;
- V3 databases, durable runtime state and the MiMo runtime bundle;
- Codex sessions, logs, plugins and active application caches;
- Playwright browsers and personal files in Downloads.

## Recurrence controls

- Next.js production builds enable the supported
  `experimental.webpackMemoryOptimizations` mode.
- The portable release smoke test now refuses to start with less than 10 GiB
  available on its temporary volume. The threshold is explicitly configurable
  through `KOLIBRI_SMOKE_MIN_FREE_KIB`.
- Multiple inactive build/dependency trees are no longer retained. Active
  `.next` output remains disposable and may be cleared between release
  candidates, but is not deleted while a server is running.

## Verification

```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/disk3s3s1  229G  182G   48G  80% /

System-wide memory free percentage: 43%
vm.swapusage: total = 0.00M used = 0.00M free = 0.00M
```

The capacity guard was also exercised with an intentionally impossible
threshold and failed closed:

```text
status=2
smoke_error=insufficient_disk
```

After the dependency-gate production build completed, the follow-up sample
still showed 45 GiB available, 73% system memory free and a 766 MiB `.next`
tree. This is the expected rebuild cost and remains well below the deleted
4.9 GiB stale canonical V3 build tree.
