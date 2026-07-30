import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  storageAdminActionsLocked,
  storageConfirmationReady,
  storageExecutionFailureIsAmbiguous,
  storageNodeAllowsActions,
  storageOperationDisposition,
  storagePreviewTarget,
} from "../lib/platform-admin/storage-ui-state.ts";

const root = path.resolve(import.meta.dirname, "..");
const read = (relative) =>
  fs.readFileSync(path.join(root, relative), "utf8");

test("storage BFF exposes bounded snapshot, preview, execute, and status-only reconcile routes", () => {
  const snapshot = read("app/api/superadmin/storage/route.ts");
  const preview = read(
    "app/api/superadmin/storage/previews/route.ts",
  );
  const execute = read(
    "app/api/superadmin/storage/operations/route.ts",
  );
  const reconcile = read(
    "app/api/superadmin/storage/operations/reconcile/route.ts",
  );
  const routes = `${snapshot}\n${preview}\n${execute}\n${reconcile}`;

  assert.match(snapshot, /\/v1\/platform-admin\/storage/);
  assert.match(preview, /\/v1\/platform-admin\/storage\/previews/);
  assert.match(execute, /\/v1\/platform-admin\/storage\/operations/);
  assert.match(
    reconcile,
    /\/v1\/platform-admin\/storage\/operations\/reconcile/,
  );
  assert.match(preview, /maxRequestBytes:\s*4\s*\*\s*1_024/);
  assert.match(execute, /maxRequestBytes:\s*2\s*\*\s*1_024/);
  assert.match(reconcile, /maxRequestBytes:\s*1\s*\*\s*1_024/);
  assert.doesNotMatch(routes, /\b(?:ssh|execFile|spawn|child_process)\b/);
  assert.doesNotMatch(routes, /\[\.\.\.|pathname|command\]/);
});

test("typed storage client is allowlisted, bounded, and fail closed", () => {
  const client = read("lib/platform-admin/storage-client.ts");

  for (const category of [
    "build",
    "cache",
    "log",
    "stopped-container",
    "project-quarantine",
  ]) {
    assert.match(client, new RegExp(`["']${category}["']`));
  }
  assert.match(client, /operationKind:\s*"cleanup"/);
  assert.match(client, /operationKind:\s*"quarantine"/);
  assert.match(client, /operationKind:\s*"restore"/);
  assert.match(client, /operationKind:\s*"restore"\s*\|\s*"purge"/);
  assert.match(client, /SAFE_PROJECT/);
  assert.match(client, /SAFE_PREVIEW/);
  assert.match(client, /StorageAdminRequestError/);
  assert.match(client, /reconcileStorageOperation/);
  assert.match(client, /policyDigest/);
  assert.match(client, /reconciled/);
  assert.match(client, /storage_reauthentication_required|code/);
  assert.match(client, /value\.categories\.length\s*>\s*5/);
  assert.match(client, /value\.projectCandidates\.length\s*>\s*100/);
  assert.match(client, /value\.quarantines\.length\s*>\s*200/);
  assert.match(client, /value\.recentOperations\.length\s*>\s*20/);
  assert.match(client, /new Set\(\s*nodes\.map/);
  assert.match(
    client,
    /value\.executeEnabled === true[\s\S]*?value\.executorStatus !== "ready"/,
  );
  assert.doesNotMatch(
    client,
    /\b(?:workspacePath|filesystemPath|shellCommand|sshCommand)\b/,
  );
});

test("storage admin UI is mobile-first and honest about unavailable execution", () => {
  const section = read(
    "components/kolibri-shell/platform-admin-section.tsx",
  );
  const panel = read("components/kolibri-shell/storage-admin.tsx");

  assert.match(section, /title="Хранилище"/);
  assert.match(section, /<StorageAdmin \/>/);
  assert.match(section, /icon=\{HardDrive\}/);
  assert.match(panel, /data-slot="storage-admin"/);
  assert.match(panel, /Home/);
  assert.match(panel, /Primary/);
  assert.match(panel, /210 GiB/);
  assert.match(panel, /19\.83 GiB/);
  assert.match(panel, /паспорт конфигурации · не live/);
  assert.match(panel, /Исполнитель узла не подключён/);
  assert.match(panel, /preview и удаление физически не работают/);
  assert.match(panel, /node\.executeEnabled/);
  assert.match(panel, /Preview restore/);
  assert.match(panel, /operationKind:\s*"restore"/);
  assert.match(panel, /purge[\s\S]*?необратимым[\s\S]*?после retention/);
  assert.match(panel, /activePreview\.preview\.confirmation/);
  assert.match(panel, /role="alert"/);
  assert.match(panel, /aria-live="polite"/);
  assert.match(panel, /sm:flex-row/);
  assert.match(panel, /w-full[\s\S]*?sm:w-auto/);
  assert.match(panel, /Кандидатов на очистку и удерживаемых проектов сейчас нет/);
  assert.doesNotMatch(panel, /\b(?:lvextend|resize2fs|docker system prune)\b/);
});

test("backend storage composition remains disabled without a trusted executor", () => {
  const main = read("backend/app/main.py");
  const executor = read("backend/app/storage_node_executor.py");
  const adapter = read("backend/app/storage_node_rust_adapter.py");
  const config = read("backend/app/config.py");
  const router = read("backend/app/storage_admin.py");

  assert.match(main, /build_storage_node_executor\(configured\)/);
  assert.match(config, /storage_executor_enabled:\s*bool\s*=\s*False/);
  assert.match(executor, /class UnavailableStorageNodeExecutor/);
  assert.match(executor, /raise StorageExecutorUnavailable\(\)/);
  assert.match(adapter, /socket\.AF_UNIX/);
  assert.match(adapter, /client\.shutdown\(socket\.SHUT_WR\)/);
  assert.match(adapter, /expected_policy_digest/);
  assert.match(adapter, /protocol_version.*v1|PROTOCOL_VERSION = "v1"/);
  assert.match(router, /platform\.storage\.manage/);
  assert.match(router, /storage_preview_authority_changed/);
  assert.match(router, /storage_node_outcome_unknown/);
  assert.match(router, /def reconcile_storage_operation/);
  const reconcileBody = router.match(
    /def reconcile_storage_operation\([\s\S]*?\n\n__all__/,
  )?.[0];
  assert.ok(reconcileBody, "reconcile endpoint must remain inspectable");
  assert.match(reconcileBody, /\.status\(/);
  assert.doesNotMatch(reconcileBody, /_executor\(request\)\.execute\(/);
  assert.match(router, /REQUIRED_STORAGE_GUARDS/);
  assert.match(router, /authoritative_project_protected/);
  assert.doesNotMatch(
    `${executor}\n${adapter}\n${router}`,
    /\b(?:paramiko|subprocess|os\.system|shlex|docker\.from_env)\b/,
  );
});

test("storage UI behavior stays fail closed across stale, preview, and retry states", () => {
  assert.equal(
    storageNodeAllowsActions({
      executorStatus: "unavailable",
      executeEnabled: false,
    }),
    false,
  );
  assert.equal(
    storageNodeAllowsActions({
      executorStatus: "ready",
      executeEnabled: true,
    }),
    true,
  );
  assert.equal(
    storageAdminActionsLocked({
      busy: false,
      loading: false,
      snapshotStale: true,
      hasActivePreview: false,
    }),
    true,
  );
  assert.equal(
    storageAdminActionsLocked({
      busy: false,
      loading: false,
      snapshotStale: false,
      hasActivePreview: false,
    }),
    false,
  );

  const preview = {
    category: "project-quarantine",
    projectId: null,
    quarantineId: "sqn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    candidateCount: 1,
    confirmation: "PURGE",
    expiresAt: 200,
  };
  assert.equal(
    storagePreviewTarget(preview, [
      {
        quarantines: [
          {
            id: preview.quarantineId,
            projectId: "legacy-project",
          },
        ],
      },
    ]),
    "legacy-project",
  );
  assert.equal(
    storageConfirmationReady(preview, "PURGE", 200),
    true,
  );
  assert.equal(
    storageConfirmationReady(preview, "purge", 200),
    false,
  );
  assert.equal(
    storageConfirmationReady(preview, "PURGE", 201),
    false,
  );
  assert.equal(
    storageConfirmationReady(preview, "PURGE", 201, true),
    true,
  );
  assert.equal(storageExecutionFailureIsAmbiguous(null), true);
  assert.equal(storageExecutionFailureIsAmbiguous(408), true);
  assert.equal(storageExecutionFailureIsAmbiguous(502), true);
  assert.equal(storageExecutionFailureIsAmbiguous(504), true);
  assert.equal(storageExecutionFailureIsAmbiguous(401), false);
  assert.equal(storageExecutionFailureIsAmbiguous(403), false);
  assert.equal(storageExecutionFailureIsAmbiguous(409), false);
  assert.equal(storageExecutionFailureIsAmbiguous(422), false);
  assert.equal(storageExecutionFailureIsAmbiguous(429), false);

  const activePreview = {
    executeKey: "storage-execute-same-key-0001",
  };
  const pending = storageOperationDisposition("pending");
  assert.equal(pending.dismissPreview, false);
  assert.equal(
    pending.dismissPreview ? null : activePreview,
    activePreview,
  );
  assert.equal(
    (pending.dismissPreview ? null : activePreview)?.executeKey,
    "storage-execute-same-key-0001",
  );
  assert.deepEqual(storageOperationDisposition("failed"), {
    alert: "failed",
    dismissPreview: true,
  });

  const panel = read("components/kolibri-shell/storage-admin.tsx");
  const loadBody = panel.match(
    /const load = useCallback\([\s\S]*?\n  }, \[\]\);/,
  )?.[0];
  assert.ok(loadBody, "load callback must remain inspectable");
  assert.doesNotMatch(loadBody, /setOperationError/);
  assert.match(panel, /sessionStorage\.setItem/);
  assert.match(panel, /Сверить status/);
  assert.match(panel, /даже после потери\s+sessionStorage/);
  assert.match(panel, /никогда не\s+повторяет execute/);
  assert.match(
    panel,
    /persistPendingRecovery\(recoveryIntent\)[\s\S]*?executeStoragePreview/,
  );
  assert.match(panel, /activePreview\.recoveryRequired/);
  assert.match(panel, /pendingOperationId/);
});
