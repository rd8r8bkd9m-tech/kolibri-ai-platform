import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import {
  chmod,
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const PORTABLE_ROOT = path.join(PROJECT_ROOT, "deploy", "portable");

function run(command, argv, options = {}) {
  const result = spawnSync(command, argv, {
    encoding: "utf8",
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  return result;
}

function requireSuccess(result, label) {
  assert.equal(
    result.status,
    0,
    `${label}\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
}

function outputValue(stdout, key) {
  const line = stdout
    .split(/\r?\n/)
    .find((candidate) => candidate.startsWith(`${key}=`));
  assert.ok(line, `missing ${key} in output:\n${stdout}`);
  return line.slice(key.length + 1);
}

async function createFixture({ standalone = false } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-release-test-"));
  const repository = standalone
    ? path.join(root, "kolibri-v3")
    : path.join(root, "repository");
  const project = standalone
    ? repository
    : path.join(repository, "kolibri-v3");
  const portable = path.join(project, "deploy", "portable");
  const verticals = path.join(project, "contracts", "v1", "verticals");
  const verticalSchemaPayload = JSON.stringify(
    {
      $schema: "https://json-schema.org/draft/2020-12/schema",
      $id: "https://schemas.kolibriai.ru/v3/vertical-pack-manifest.schema.json",
      type: "object",
    },
    null,
    2,
  ) + "\n";
  const verticalSchemaDigest = createHash("sha256")
    .update(verticalSchemaPayload)
    .digest("hex");
  await mkdir(path.join(project, "app"), { recursive: true });
  await mkdir(path.join(project, "app", "api", "live"), { recursive: true });
  await mkdir(path.join(project, "backend", "app"), { recursive: true });
  await mkdir(path.join(project, "backend", "migrations"), { recursive: true });
  await mkdir(path.join(project, "contracts", "generated", "v1"), {
    recursive: true,
  });
  await mkdir(path.join(verticals, "examples"), { recursive: true });
  await mkdir(path.join(project, "generated"), { recursive: true });
  await mkdir(portable, { recursive: true });
  await mkdir(path.join(project, "deploy", "workers"), { recursive: true });
  await mkdir(path.join(project, "server"), { recursive: true });

  await Promise.all([
    writeFile(path.join(project, "app", "layout.tsx"), "export default 1;\n"),
    writeFile(
      path.join(project, "app", "api", "live", "route.ts"),
      "export function GET() { return Response.json({ status: 'ok' }); }\n",
    ),
    writeFile(path.join(project, "backend", "app", "main.py"), "app = None\n"),
    writeFile(
      path.join(project, "backend", "app", "product_run_worker.py"),
      "def main(): pass\n",
    ),
    writeFile(
      path.join(project, "backend", "app", "provider_enrollment_worker.py"),
      "def main(): pass\n",
    ),
    writeFile(
      path.join(project, "backend", "app", "release_monitor.py"),
      "def main(): pass\n",
    ),
    writeFile(
      path.join(project, "backend", "app", "runtime_readiness.py"),
      "def product_worker_is_ready(*args, **kwargs): return True\n",
    ),
    writeFile(path.join(project, "backend", "requirements.txt"), "fastapi\n"),
    writeFile(
      path.join(project, "backend", "migrations", "001_core.sql"),
      "PRAGMA user_version = 1;\n",
    ),
    writeFile(
      path.join(project, "backend", "migrations", "032_mobile.sql"),
      "PRAGMA user_version = 32;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "033_platform_admin_control_plane.sql",
      ),
      "PRAGMA user_version = 33;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "034_trusted_agent_control_plane.sql",
      ),
      "PRAGMA user_version = 34;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "035_platform_audit_read_capability.sql",
      ),
      "PRAGMA user_version = 35;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "036_trusted_agent_execution_binding.sql",
      ),
      "PRAGMA user_version = 36;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "037_trusted_agent_lease_lifecycle.sql",
      ),
      "PRAGMA user_version = 37;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "038_product_entitlement_projection.sql",
      ),
      "PRAGMA user_version = 38;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "039_durable_direct_run_outbox.sql",
      ),
      "PRAGMA user_version = 39;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "040_bounded_attachments.sql",
      ),
      "PRAGMA user_version = 40;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "041_generated_image_artifacts.sql",
      ),
      "PRAGMA user_version = 41;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "042_storage_admin_control_plane.sql",
      ),
      "PRAGMA user_version = 42;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "043_storage_admin_restore_reconcile.sql",
      ),
      "PRAGMA user_version = 43;\n",
    ),
    writeFile(
      path.join(
        project,
        "backend",
        "migrations",
        "044_runtime_worker_heartbeats.sql",
      ),
      "PRAGMA user_version = 44;\n",
    ),
    writeFile(
      path.join(project, "contracts", "generated", "v1", "manifest.json"),
      JSON.stringify(
        {
          contract_count: 0,
          generator_version: "1.0",
          outputs: [
            "generated/contracts-v1.ts",
            "server/contracts_runtime.py",
          ],
          schema_count: 1,
          schema_id: "kolibri.generated_contract_package_manifest",
          schema_version: "1.0",
          schemas: [
            {
              schema_uri:
                "https://schemas.kolibriai.ru/v3/vertical-pack-manifest.schema.json",
              sha256: verticalSchemaDigest,
              source_path:
                "contracts/v1/verticals/vertical-pack-manifest.schema.json",
            },
          ],
        },
        null,
        2,
      ) + "\n",
    ),
    writeFile(
      path.join(verticals, "vertical-pack-manifest.schema.json"),
      verticalSchemaPayload,
    ),
    writeFile(
      path.join(verticals, "examples", "construction-estimates.json"),
      '{"vertical_id":"construction.estimates"}\n',
    ),
    writeFile(
      path.join(project, "generated", "contracts-v1.ts"),
      "export const generatedContracts = {};\n",
    ),
    writeFile(
      path.join(project, "server", "contracts_runtime.py"),
      "class ContractBoundaryClient: pass\n",
    ),
    writeFile(
      path.join(project, "server", "generate_contract_manifest.py"),
      "raise SystemExit(0)\n",
    ),
    writeFile(
      path.join(project, "deploy", "workers", "worker_launcher.py"),
      "#!/usr/bin/env python3\n",
    ),
    writeFile(
      path.join(
        project,
        "deploy",
        "workers",
        "kolibri-v3-estimate-reconciliation-audit.service.in",
      ),
      "[Service]\n",
    ),
    writeFile(
      path.join(
        project,
        "deploy",
        "workers",
        "kolibri-v3-product-run-worker.service.in",
      ),
      "[Service]\n",
    ),
    writeFile(
      path.join(
        project,
        "deploy",
        "workers",
        "kolibri-v3-provider-enrollment-worker.service.in",
      ),
      "[Service]\n",
    ),
    writeFile(
      path.join(project, "deploy", "workers", "workers.env.example"),
      "KOLIBRI_V3_DATABASE_URL=\n",
    ),
    writeFile(path.join(project, "package.json"), '{"private":true}\n'),
    writeFile(path.join(project, "package-lock.json"), '{"lockfileVersion":3}\n'),
    copyFile(
      path.join(PORTABLE_ROOT, "build-release.sh"),
      path.join(portable, "build-release.sh"),
    ),
    copyFile(
      path.join(PORTABLE_ROOT, "database-rehearsal.py"),
      path.join(portable, "database-rehearsal.py"),
    ),
    copyFile(
      path.join(PORTABLE_ROOT, "install-contract.py"),
      path.join(portable, "install-contract.py"),
    ),
    copyFile(
      path.join(PORTABLE_ROOT, "install.sh"),
      path.join(portable, "install.sh"),
    ),
    copyFile(
      path.join(PORTABLE_ROOT, "release-manifest.py"),
      path.join(portable, "release-manifest.py"),
    ),
    copyFile(
      path.join(PORTABLE_ROOT, "smoke-test.sh"),
      path.join(portable, "smoke-test.sh"),
    ),
  ]);
  await Promise.all([
    chmod(path.join(portable, "build-release.sh"), 0o755),
    chmod(path.join(portable, "database-rehearsal.py"), 0o755),
    chmod(path.join(portable, "install-contract.py"), 0o755),
    chmod(path.join(portable, "install.sh"), 0o755),
    chmod(path.join(portable, "release-manifest.py"), 0o755),
    chmod(path.join(portable, "smoke-test.sh"), 0o755),
  ]);

  requireSuccess(run("git", ["init", "-q", repository]), "git init");
  requireSuccess(
    run("git", [
      "-C",
      repository,
      "add",
      standalone ? "." : "kolibri-v3",
    ]),
    "git add",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "fixture",
      ],
      {
        env: {
          ...process.env,
          GIT_AUTHOR_DATE: "2026-07-30T00:00:00Z",
          GIT_COMMITTER_DATE: "2026-07-30T00:00:00Z",
        },
      },
    ),
    "git commit",
  );
  return { root, repository, project, portable };
}

test("canonical V3 exposes only the self-contained portable release lane", async () => {
  for (const relativePath of [
    "deploy/install-home.sh",
    "deploy/kolibri-v3-backend.service",
    "deploy/kolibri-v3-frontend.service",
    "deploy/nginx-kolibriai.conf",
  ]) {
    assert.equal(
      existsSync(path.join(PROJECT_ROOT, relativePath)),
      false,
      `${relativePath} must not remain as an alternate release entry point`,
    );
  }
  const testSource = await readFile(fileURLToPath(import.meta.url), "utf8");
  for (const forbiddenReference of [
    ["REPO", "ROOT"].join("_"),
    ["release", "kolibri", "v3", "product.sh"].join("_"),
  ]) {
    assert.equal(
      testSource.includes(forbiddenReference),
      false,
      `portable tests must not depend on ${forbiddenReference}`,
    );
  }
  for (const relativePath of [
    "deploy/portable/build-release.sh",
    "deploy/portable/database-rehearsal.py",
    "deploy/portable/install.sh",
    "deploy/portable/smoke-test.sh",
    "deploy/portable/install-contract.py",
    "deploy/workers/worker_launcher.py",
  ]) {
    const source = await readFile(path.join(PROJECT_ROOT, relativePath), "utf8");
    assert.doesNotMatch(
      source,
      /kolibri-backend|(?:[.][.]\/)+(?:ops|contracts|tests)(?:\/|["'])/,
      `${relativePath} must not depend on a parent or legacy runtime`,
    );
  }
});

test("portable archive binds canonical backend, web, Git, migrations, and stable content", async (t) => {
  const fixture = await createFixture();
  t.after(() => rm(fixture.root, { recursive: true, force: true }));
  const outputA = path.join(fixture.root, "output-a");
  const outputB = path.join(fixture.root, "another", "output-b");

  const first = run(
    "bash",
    [path.join(fixture.portable, "build-release.sh"), outputA],
    { cwd: fixture.project },
  );
  requireSuccess(first, "first portable build");
  const second = run(
    "bash",
    [path.join(fixture.portable, "build-release.sh"), outputB],
    { cwd: fixture.project },
  );
  requireSuccess(second, "second portable build");

  const archiveA = outputValue(first.stdout, "release_archive");
  const archiveB = outputValue(second.stdout, "release_archive");
  assert.equal(
    outputValue(first.stdout, "release_content_digest"),
    outputValue(second.stdout, "release_content_digest"),
  );
  assert.equal(
    outputValue(first.stdout, "release_sha256"),
    outputValue(second.stdout, "release_sha256"),
  );
  assert.equal(
    outputValue(first.stdout, "release_lane"),
    "canonical-portable-only",
  );
  assert.deepEqual(await readFile(archiveA), await readFile(archiveB));

  const manifest = JSON.parse(
    await readFile(`${archiveA}.manifest.json`, "utf8"),
  );
  assert.equal(manifest.format, "kolibri-v3-portable-v2");
  assert.match(manifest.release_id, /^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}$/);
  assert.match(manifest.git_commit_sha, /^[0-9a-f]{40}$/);
  assert.equal(manifest.source_commit, manifest.git_commit_sha);
  assert.match(manifest.git_tree_sha, /^[0-9a-f]{40}$/);
  assert.match(manifest.package_sha256, /^[0-9a-f]{64}$/);
  assert.match(manifest.content_digest, /^[0-9a-f]{64}$/);
  assert.equal(manifest.source_tree_sha256, manifest.content_digest);
  assert.match(manifest.gate_input_digest, /^[0-9a-f]{64}$/);
  assert.equal(manifest.migration_minimum_version, "001");
  assert.equal(manifest.migration_maximum_version, "044");
  assert.equal(manifest.migration_count, 14);
  assert.equal(manifest.release_lane, "canonical-portable-only");
  assert.equal(manifest.dirty, false);

  const verify = run(
    "python3",
    [
      path.join(fixture.portable, "release-manifest.py"),
      "verify",
      "--archive",
      archiveA,
    ],
    { cwd: fixture.project },
  );
  requireSuccess(verify, "portable verify");
  assert.match(verify.stdout, /release_verify=ok/);

  const descriptorVerify = run("bash", [
    "-c",
    [
      'exec 7<"$1"',
      'exec 8<"$1.manifest.json"',
      'exec 6<"$1.sha256"',
      'python3 "$2" verify --archive /dev/fd/7 --archive-name "$3" --manifest /dev/fd/8 --checksum /dev/fd/6',
      'python3 "$2" verify --archive /dev/fd/7 --archive-name "$3" --manifest /dev/fd/8 --checksum /dev/fd/6',
      "tar -tzf /dev/fd/7 >/dev/null",
    ].join("\n"),
    "descriptor-verify",
    archiveA,
    path.join(fixture.portable, "release-manifest.py"),
    path.basename(archiveA),
  ]);
  requireSuccess(descriptorVerify, "descriptor-bound portable verify");
  assert.match(descriptorVerify.stdout, /release_verify=ok/);

  const listing = run("tar", ["-tzf", archiveA]);
  requireSuccess(listing, "archive listing");
  assert.match(listing.stdout, /kolibri-v3\/app\/layout[.]tsx/);
  assert.match(listing.stdout, /kolibri-v3\/backend\/app\/main[.]py/);
  assert.match(
    listing.stdout,
    /kolibri-v3\/deploy\/workers\/worker_launcher[.]py/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/deploy\/workers\/kolibri-v3-product-run-worker[.]service[.]in/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/034_trusted_agent_control_plane[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/035_platform_audit_read_capability[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/036_trusted_agent_execution_binding[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/037_trusted_agent_lease_lifecycle[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/038_product_entitlement_projection[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/039_durable_direct_run_outbox[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/040_bounded_attachments[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/041_generated_image_artifacts[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/042_storage_admin_control_plane[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/043_storage_admin_restore_reconcile[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/migrations\/044_runtime_worker_heartbeats[.]sql/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/backend\/app\/release_monitor[.]py/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/server\/contracts_runtime[.]py/,
  );
  assert.match(
    listing.stdout,
    /kolibri-v3\/contracts\/v1\/verticals\/vertical-pack-manifest[.]schema[.]json/,
  );
  assert.match(listing.stdout, /kolibri-v3\/RELEASE_PROVENANCE[.]json/);
  assert.match(listing.stdout, /kolibri-v3\/MIGRATIONS[.]sha256/);
  assert.doesNotMatch(listing.stdout, /kolibri-backend/);
  assert.doesNotMatch(listing.stdout, /kolibri-v3\/deploy\/install-home[.]sh/);

  const contentManifest = run("tar", [
    "-xOzf",
    archiveA,
    "kolibri-v3/RELEASE_CONTENTS.sha256",
  ]);
  requireSuccess(contentManifest, "content manifest read");
  assert.doesNotMatch(contentManifest.stdout, new RegExp(fixture.root));
  assert.match(contentManifest.stdout, /  backend\/app\/main[.]py/);

  const provenanceResult = run("tar", [
    "-xOzf",
    archiveA,
    "kolibri-v3/RELEASE_PROVENANCE.json",
  ]);
  requireSuccess(provenanceResult, "release provenance read");
  const provenance = JSON.parse(provenanceResult.stdout);
  assert.equal(provenance.release_id, manifest.release_id);
  assert.equal(provenance.source_commit, manifest.git_commit_sha);
  assert.equal(provenance.source_tree_sha256, manifest.content_digest);
  assert.equal(provenance.gate_input_digest, manifest.gate_input_digest);
  assert.equal(provenance.gates.release_lane, "canonical-portable-only");
  assert.equal(provenance.dirty, false);
  assert.equal(provenance.builder.name, "kolibri-v3-portable-release-manifest");
  assert.equal(provenance.components.web, "app");
  assert.equal(provenance.components.backend, "backend");
  assert.equal(
    provenance.components.persistent_database,
    "/opt/kolibri-v3/var/kolibri-v3.db",
  );
  assert.equal(provenance.activation_preconditions.database_mode, "0600");
  assert.equal(provenance.activation_preconditions.database_sidecar_mode, "0600");
  assert.equal(provenance.activation_preconditions.backend_systemd_umask, "0077");
});

test("portable builder is self-contained when kolibri-v3 is the repository root", async (t) => {
  const fixture = await createFixture({ standalone: true });
  t.after(() => rm(fixture.root, { recursive: true, force: true }));
  const result = run(
    "bash",
    [
      path.join(fixture.portable, "build-release.sh"),
      path.join(fixture.root, "output"),
    ],
    { cwd: fixture.project },
  );
  requireSuccess(result, "standalone portable build");
  const archive = outputValue(result.stdout, "release_archive");
  const verify = run("python3", [
    path.join(fixture.portable, "release-manifest.py"),
    "verify",
    "--archive",
    archive,
  ]);
  requireSuccess(verify, "standalone portable verify");
  assert.match(verify.stdout, /release_verify=ok/);
});

test("portable builder rejects dirty source and verifier rejects package tampering", async (t) => {
  const fixture = await createFixture();
  t.after(() => rm(fixture.root, { recursive: true, force: true }));
  const output = path.join(fixture.root, "output");

  const cleanBuild = run(
    "bash",
    [path.join(fixture.portable, "build-release.sh"), output],
    { cwd: fixture.project },
  );
  requireSuccess(cleanBuild, "clean portable build");
  const archive = outputValue(cleanBuild.stdout, "release_archive");

  await writeFile(path.join(fixture.project, "app", "layout.tsx"), "dirty\n");
  const dirtyBuild = run(
    "bash",
    [path.join(fixture.portable, "build-release.sh"), output],
    { cwd: fixture.project },
  );
  assert.equal(dirtyBuild.status, 2);
  assert.match(dirtyBuild.stderr, /project_has_uncommitted_changes/);

  const original = await readFile(archive);
  const tampered = Buffer.from(original);
  tampered[tampered.length - 9] ^= 0x01;
  await writeFile(archive, tampered);
  const verify = run("python3", [
    path.join(fixture.portable, "release-manifest.py"),
    "verify",
    "--archive",
    archive,
  ]);
  assert.equal(verify.status, 3);
  assert.match(verify.stderr, /package_sha256_mismatch/);
});

test("portable builder rejects a committed legacy backend payload", async (t) => {
  const fixture = await createFixture();
  t.after(() => rm(fixture.root, { recursive: true, force: true }));
  const legacyBackend = path.join(
    fixture.project,
    "kolibri-backend",
    "app",
  );
  await mkdir(legacyBackend, { recursive: true });
  await writeFile(path.join(legacyBackend, "main.py"), "legacy = True\n");
  requireSuccess(
    run("git", ["-C", fixture.repository, "add", "kolibri-v3"]),
    "git add legacy fixture",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        fixture.repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "legacy payload",
      ],
    ),
    "git commit legacy fixture",
  );

  const result = run(
    "bash",
    [
      path.join(fixture.portable, "build-release.sh"),
      path.join(fixture.root, "output"),
    ],
    { cwd: fixture.project },
  );
  assert.equal(result.status, 3);
  assert.match(result.stderr, /legacy_backend_forbidden/);
  assert.doesNotMatch(result.stdout, /release_archive=/);
});

test("portable builder rejects parent-level V3 release entrypoints", async (t) => {
  const activeHelper = await createFixture();
  const changedTombstone = await createFixture();
  t.after(() => rm(activeHelper.root, { recursive: true, force: true }));
  t.after(() => rm(changedTombstone.root, { recursive: true, force: true }));

  const activeHelperPath = path.join(
    activeHelper.repository,
    "ops",
    "release",
    "kolibri_v3_home_apply.sh",
  );
  await mkdir(path.dirname(activeHelperPath), { recursive: true });
  await writeFile(activeHelperPath, "#!/usr/bin/env bash\nexit 0\n");
  requireSuccess(
    run("git", ["-C", activeHelper.repository, "add", "ops"]),
    "git add parent release helper",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        activeHelper.repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "parent release helper",
      ],
    ),
    "git commit parent release helper",
  );
  const activeResult = run(
    "bash",
    [
      path.join(activeHelper.portable, "build-release.sh"),
      path.join(activeHelper.root, "output"),
    ],
    { cwd: activeHelper.project },
  );
  assert.equal(activeResult.status, 3);
  assert.match(
    activeResult.stderr,
    /repository_alternate_release_lane_forbidden/,
  );
  assert.doesNotMatch(activeResult.stdout, /release_archive=/);

  const coordinatorName = [
    "release",
    "kolibri",
    "v3",
    "product.sh",
  ].join("_");
  const coordinatorPath = path.join(
    changedTombstone.repository,
    "ops",
    coordinatorName,
  );
  await mkdir(path.dirname(coordinatorPath), { recursive: true });
  await writeFile(coordinatorPath, "#!/usr/bin/env bash\nexit 0\n");
  requireSuccess(
    run("git", ["-C", changedTombstone.repository, "add", "ops"]),
    "git add changed tombstone",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        changedTombstone.repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "changed tombstone",
      ],
    ),
    "git commit changed tombstone",
  );
  const tombstoneResult = run(
    "bash",
    [
      path.join(changedTombstone.portable, "build-release.sh"),
      path.join(changedTombstone.root, "output"),
    ],
    { cwd: changedTombstone.project },
  );
  assert.equal(tombstoneResult.status, 3);
  assert.match(
    tombstoneResult.stderr,
    /legacy_release_tombstone_changed/,
  );
  assert.doesNotMatch(tombstoneResult.stdout, /release_archive=/);
});

test("portable builder rejects alternate release lanes and stale contract manifests", async (t) => {
  const alternate = await createFixture();
  const staleManifest = await createFixture();
  const leakedSecret = await createFixture();
  t.after(() => rm(alternate.root, { recursive: true, force: true }));
  t.after(() => rm(staleManifest.root, { recursive: true, force: true }));
  t.after(() => rm(leakedSecret.root, { recursive: true, force: true }));

  await writeFile(
    path.join(alternate.project, "deploy", "install-home.sh"),
    "#!/usr/bin/env bash\nexit 0\n",
  );
  requireSuccess(
    run("git", ["-C", alternate.repository, "add", "kolibri-v3"]),
    "git add alternate release lane",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        alternate.repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "alternate lane",
      ],
    ),
    "git commit alternate release lane",
  );
  const alternateResult = run(
    "bash",
    [
      path.join(alternate.portable, "build-release.sh"),
      path.join(alternate.root, "output"),
    ],
    { cwd: alternate.project },
  );
  assert.equal(alternateResult.status, 3);
  assert.match(alternateResult.stderr, /alternate_release_lane_forbidden/);

  const manifestPath = path.join(
    staleManifest.project,
    "contracts",
    "generated",
    "v1",
    "manifest.json",
  );
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  manifest.schemas[0].sha256 = "0".repeat(64);
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  requireSuccess(
    run("git", ["-C", staleManifest.repository, "add", "kolibri-v3"]),
    "git add stale manifest",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        staleManifest.repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "stale manifest",
      ],
    ),
    "git commit stale manifest",
  );
  const manifestResult = run(
    "bash",
    [
      path.join(staleManifest.portable, "build-release.sh"),
      path.join(staleManifest.root, "output"),
    ],
    { cwd: staleManifest.project },
  );
  assert.equal(manifestResult.status, 3);
  assert.match(
    manifestResult.stderr,
    /contract_schema_integrity_mismatch/,
  );

  await writeFile(
    path.join(leakedSecret.project, "app", "leaked-token.txt"),
    "sk-" + "a".repeat(32) + "\n",
  );
  requireSuccess(
    run("git", ["-C", leakedSecret.repository, "add", "kolibri-v3"]),
    "git add leaked secret",
  );
  requireSuccess(
    run(
      "git",
      [
        "-C",
        leakedSecret.repository,
        "-c",
        "user.name=Kolibri Release Test",
        "-c",
        "user.email=release-test@invalid.example",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "leaked secret",
      ],
    ),
    "git commit leaked secret",
  );
  const secretResult = run(
    "bash",
    [
      path.join(leakedSecret.portable, "build-release.sh"),
      path.join(leakedSecret.root, "output"),
    ],
    { cwd: leakedSecret.project },
  );
  assert.equal(secretResult.status, 3);
  assert.match(secretResult.stderr, /secret_token_material_forbidden/);
  assert.doesNotMatch(secretResult.stdout, /release_archive=/);
});

test("portable builder rejects credential files and expanded token families", async (t) => {
  const cases = [
    {
      relativePath: ".npmrc",
      payload: "registry=https://registry.npmjs.org/\n",
      expected: /secret_or_mutable_file_forbidden/,
    },
    {
      relativePath: "apps/kolibri-mobile/AuthKey_TEST123456.p8",
      payload: "synthetic signing material\n",
      expected: /secret_or_mutable_file_forbidden/,
    },
    {
      relativePath: "app/leaked-slack-token.txt",
      payload: "xoxb-" + "a".repeat(32) + "\n",
      expected: /kind=slack_token/,
    },
    {
      relativePath: "app/leaked-registry-token.txt",
      payload: "NPM_TOKEN=" + "b".repeat(32) + "\n",
      expected: /kind=credential_assignment/,
    },
    {
      relativePath: "app/leaked-basic-auth-url.txt",
      payload: "https://release-user:" + "c".repeat(24) + "@example.test/\n",
      expected: /kind=basic_auth_url/,
    },
  ];

  for (const [index, scenario] of cases.entries()) {
    const fixture = await createFixture();
    t.after(() => rm(fixture.root, { recursive: true, force: true }));
    const target = path.join(fixture.project, scenario.relativePath);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, scenario.payload);
    requireSuccess(
      run("git", ["-C", fixture.repository, "add", "kolibri-v3"]),
      `git add credential scenario ${index}`,
    );
    requireSuccess(
      run(
        "git",
        [
          "-C",
          fixture.repository,
          "-c",
          "user.name=Kolibri Release Test",
          "-c",
          "user.email=release-test@invalid.example",
          "-c",
          "commit.gpgsign=false",
          "commit",
          "-q",
          "-m",
          `credential scenario ${index}`,
        ],
      ),
      `git commit credential scenario ${index}`,
    );
    const result = run(
      "bash",
      [
        path.join(fixture.portable, "build-release.sh"),
        path.join(fixture.root, "output"),
      ],
      { cwd: fixture.project },
    );
    assert.equal(result.status, 3);
    assert.match(result.stderr, scenario.expected);
    assert.doesNotMatch(result.stdout, /release_archive=/);
  }
});

test("smoke test accepts only a verified canonical release archive", async () => {
  const smoke = await readFile(
    path.join(PORTABLE_ROOT, "smoke-test.sh"),
    "utf8",
  );
  assert.match(smoke, /release_archive_required/);
  assert.match(smoke, /release-manifest[.]py"\s+verify\s+--archive/);
  assert.match(smoke, /project_root="\$work_root\/kolibri-v3"/);
  assert.match(smoke, /KOLIBRI_SMOKE_MIN_FREE_KIB/);
  assert.match(smoke, /smoke_error=insufficient_disk/);
  assert.match(
    smoke,
    /work_root="\$\(cd -- "\$work_root" && pwd -P\)"/,
  );
  assert.match(smoke, /KOLIBRI_V3_ENV=production/);
  assert.doesNotMatch(smoke, /KOLIBRI_V3_ENV=development/);
  assert.match(
    smoke,
    /KOLIBRI_RELEASE_ID="\$release_id"[\s\S]+KOLIBRI_RELEASE_COMMIT="\$release_commit"[\s\S]+npm run build/,
  );
  assert.match(
    smoke,
    /cd "\$project_root\/backend"[\s\S]+worker_launcher[.]py" product-run/,
  );
  assert.match(smoke, /KOLIBRI_WORKER_EXPECTED_DATABASE_URL=/);
  assert.match(smoke, /KOLIBRI_WORKER_LOCK_PATH=/);
  assert.match(smoke, /chmod 600 "\$work_root\/kolibri-v3[.]db"/);
  assert.doesNotMatch(smoke, /-m app[.]product_run_worker/);
  assert.match(smoke, /\/v1\/ready/);
  assert.match(smoke, /x-kolibri-release/);
  assert.doesNotMatch(smoke, /-C "\$project_root" -cf - [.] \|/);
});

test("install contract renders fail-closed workers with managed release precedence", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-workers-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const output = path.join(root, "rendered");
  await mkdir(output);

  const result = run("python3", [
    path.join(PORTABLE_ROOT, "install-contract.py"),
    "render-workers",
    "--source-root",
    await realpath(path.join(PROJECT_ROOT, "deploy", "workers")),
    "--output-dir",
    await realpath(output),
    "--instance",
    "kolibri-v3",
    "--install-root",
    "/opt/kolibri-v3",
    "--config-root",
    "/etc/kolibri-v3",
    "--service-user",
    "kolibri",
    "--service-group",
    "kolibri",
    "--backend-service",
    "kolibri-v3-backend.service",
  ]);
  requireSuccess(result, "worker render");
  assert.match(result.stdout, /worker_render=ok/);

  for (const role of [
    "product-run-worker",
    "provider-enrollment-worker",
    "estimate-reconciliation-audit",
  ]) {
    const payload = await readFile(
      path.join(output, `kolibri-v3-${role}.service`),
      "utf8",
    );
    assert.doesNotMatch(payload, /@[A-Z_]+@/);
    assert.match(payload, /UMask=0077/);
    assert.ok(
      payload.indexOf("EnvironmentFile=/etc/kolibri-v3/backend.env") <
        payload.indexOf("EnvironmentFile=/etc/kolibri-v3/release.env"),
    );
    assert.match(payload, /worker_launcher[.]py .* --check/);
  }
});

test("install contract renders exact fail-closed monitor and backup units", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-operations-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const output = path.join(root, "rendered");
  await mkdir(output);

  const result = run("python3", [
    path.join(PORTABLE_ROOT, "install-contract.py"),
    "render-operations",
    "--output-dir",
    await realpath(output),
    "--instance",
    "kolibri-v3",
    "--current-link",
    "/opt/kolibri-v3/current",
    "--service-user",
    "kolibri-v3",
    "--service-group",
    "kolibri-v3",
    "--service-uid",
    "1001",
    "--data-root",
    "/opt/kolibri-v3/var",
    "--backup-root",
    "/var/backups/kolibri-v3",
    "--backend-port",
    "8002",
    "--frontend-port",
    "3103",
    "--public-origin",
    "https://kolibriai.ru",
    "--release-id",
    "kolibri-v3-0123456789ab-abcdef012345",
    "--release-commit",
    "0123456789abcdef0123456789abcdef01234567",
    "--expected-schema",
    "44",
    "--systemctl",
    "/usr/bin/systemctl",
    "--journalctl",
    "/usr/bin/journalctl",
    "--database-helper",
    "/opt/kolibri-v3/libexec/database-rehearsal.py",
  ]);
  requireSuccess(result, "operation unit render");
  assert.match(result.stdout, /operation_render=ok/);

  const monitor = await readFile(
    path.join(output, "kolibri-v3-release-monitor.service"),
    "utf8",
  );
  const monitorTimer = await readFile(
    path.join(output, "kolibri-v3-release-monitor.timer"),
    "utf8",
  );
  const backup = await readFile(
    path.join(output, "kolibri-v3-database-backup.service"),
    "utf8",
  );
  const backupTimer = await readFile(
    path.join(output, "kolibri-v3-database-backup.timer"),
    "utf8",
  );

  for (const payload of [monitor, monitorTimer, backup, backupTimer]) {
    assert.doesNotMatch(payload, /@[A-Z_]+@/);
  }
  assert.match(monitor, /-m app[.]release_monitor/);
  assert.match(monitor, /--public-url https:\/\/kolibriai[.]ru\/readyz/);
  assert.match(monitor, /^User=kolibri-v3$/m);
  assert.match(monitor, /^Group=kolibri-v3$/m);
  assert.match(monitor, /--backup-owner-uid 1001/);
  assert.match(monitor, /^CapabilityBoundingSet=$/m);
  assert.match(monitor, /^ReadWritePaths=\/opt\/kolibri-v3\/var$/m);
  assert.doesNotMatch(
    monitor,
    /^ReadOnlyPaths=.*\/opt\/kolibri-v3\/var(?:\s|$)/m,
  );
  assert.doesNotMatch(monitor, /^Requires=.*(?:backend|frontend|worker)/m);
  assert.match(monitorTimer, /OnUnitActiveSec=60s/);
  assert.match(backup, /database-rehearsal[.]py scheduled-backup/);
  assert.match(backup, /PrivateNetwork=true/);
  assert.match(
    backup,
    /^ReadWritePaths=\/opt\/kolibri-v3\/var \/var\/backups\/kolibri-v3$/m,
  );
  assert.doesNotMatch(
    backup,
    /^ReadOnlyPaths=.*\/opt\/kolibri-v3\/var(?:\s|$)/m,
  );
  assert.doesNotMatch(backup, /^Requires=.*backend/m);
  assert.match(backupTimer, /OnCalendar=[*]-[*]-[*] 02:15:00 UTC/);

  const unsafe = run("python3", [
    path.join(PORTABLE_ROOT, "install-contract.py"),
    "render-operations",
    "--output-dir",
    await realpath(output),
    "--instance",
    "kolibri-v3",
    "--current-link",
    "/opt/kolibri-v3/current",
    "--service-user",
    "kolibri-v3",
    "--service-group",
    "kolibri-v3",
    "--service-uid",
    "1001",
    "--data-root",
    "/opt/kolibri-v3/var",
    "--backup-root",
    "/var/backups/kolibri-v3",
    "--backend-port",
    "8002",
    "--frontend-port",
    "3103",
    "--public-origin",
    "http://kolibriai.ru",
    "--release-id",
    "kolibri-v3-0123456789ab-abcdef012345",
    "--release-commit",
    "0123456789abcdef0123456789abcdef01234567",
    "--expected-schema",
    "44",
    "--systemctl",
    "/usr/bin/systemctl",
    "--journalctl",
    "/usr/bin/journalctl",
    "--database-helper",
    "/opt/kolibri-v3/libexec/database-rehearsal.py",
  ]);
  assert.equal(unsafe.status, 3);
  assert.match(unsafe.stderr, /operation_public_origin_invalid/);
});

test("install contract converges SQLite files and rejects a database symlink", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-database-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const canonicalRoot = await realpath(root);
  for (const name of [
    "kolibri-v3.db",
    "kolibri-v3.db-wal",
    "kolibri-v3.db-shm",
  ]) {
    await writeFile(path.join(canonicalRoot, name), name, { mode: 0o644 });
    await chmod(path.join(canonicalRoot, name), 0o644);
  }

  const normalized = run("python3", [
    path.join(PORTABLE_ROOT, "install-contract.py"),
    "normalize-database",
    "--data-root",
    canonicalRoot,
    "--service-uid",
    String(process.getuid()),
    "--service-gid",
    String(process.getgid()),
  ]);
  requireSuccess(normalized, "database permission convergence");
  assert.match(normalized.stdout, /database_files_normalized=3/);
  assert.equal((await stat(canonicalRoot)).mode & 0o777, 0o700);
  for (const name of [
    "kolibri-v3.db",
    "kolibri-v3.db-wal",
    "kolibri-v3.db-shm",
  ]) {
    assert.equal((await stat(path.join(canonicalRoot, name))).mode & 0o777, 0o600);
  }

  const unsafeRoot = path.join(canonicalRoot, "unsafe");
  await mkdir(unsafeRoot, { mode: 0o700 });
  await symlink(
    path.join(canonicalRoot, "kolibri-v3.db"),
    path.join(unsafeRoot, "kolibri-v3.db"),
  );
  const rejected = run("python3", [
    path.join(PORTABLE_ROOT, "install-contract.py"),
    "normalize-database",
    "--data-root",
    await realpath(unsafeRoot),
    "--service-uid",
    String(process.getuid()),
    "--service-gid",
    String(process.getgid()),
  ]);
  assert.equal(rejected.status, 3);
  assert.match(rejected.stderr, /database_path_unsafe/);
});

test("database rehearsal creates an exact restorable snapshot and rolls back its write probe", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-recovery-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const canonicalRoot = await realpath(root);
  const source = path.join(canonicalRoot, "source.db");
  const rehearsal = path.join(canonicalRoot, "rehearsal");
  const helper = path.join(PORTABLE_ROOT, "database-rehearsal.py");
  await mkdir(rehearsal, { mode: 0o700 });
  await chmod(rehearsal, 0o700);

  const seeded = run("python3", [
    "-c",
    [
      "import sqlite3, sys",
      "db = sqlite3.connect(sys.argv[1])",
      "db.execute('CREATE TABLE tenants(id TEXT PRIMARY KEY, name TEXT NOT NULL)')",
      "db.execute('CREATE TABLE projects(id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id))')",
      "db.execute('INSERT INTO tenants VALUES (?, ?)', ('tenant-1', 'Kolibri'))",
      "db.execute('INSERT INTO projects VALUES (?, ?)', ('project-1', 'tenant-1'))",
      "db.execute('PRAGMA user_version = 43')",
      "db.commit()",
      "db.close()",
    ].join(";"),
    source,
  ]);
  requireSuccess(seeded, "seed recovery database");

  const result = run("python3", [
    helper,
    "rehearse",
    "--source",
    source,
    "--work-dir",
    rehearsal,
    "--expected-version",
    "43",
  ]);
  requireSuccess(result, "database recovery rehearsal");
  assert.match(result.stdout, /database_rehearsal=ok/);
  assert.match(result.stdout, /database_schema_version=43/);
  assert.match(result.stdout, /database_write_probe=rolled_back/);
  assert.match(result.stdout, /database_snapshot_sha256=[0-9a-f]{64}/);

  const backup = path.join(rehearsal, "kolibri-v3.backup.db");
  const restored = path.join(rehearsal, "kolibri-v3.restored.db");
  assert.equal((await stat(backup)).mode & 0o777, 0o600);
  assert.equal((await stat(restored)).mode & 0o777, 0o600);
  assert.deepEqual(await readFile(restored), await readFile(backup));

  const verified = run("python3", [
    "-c",
    [
      "import sqlite3, sys",
      "db = sqlite3.connect(sys.argv[1])",
      "assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'",
      "assert db.execute('PRAGMA foreign_key_check').fetchone() is None",
      "assert db.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 1",
      "assert db.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE name='__kolibri_database_recovery_probe'\").fetchone()[0] == 0",
      "db.close()",
    ].join(";"),
    restored,
  ]);
  requireSuccess(verified, "verify restored database");

  const scheduledRoot = path.join(canonicalRoot, "scheduled-backups");
  await mkdir(scheduledRoot, { mode: 0o700 });
  await chmod(scheduledRoot, 0o700);
  const scheduledArguments = [
    helper,
    "scheduled-backup",
    "--source",
    source,
    "--backup-root",
    scheduledRoot,
    "--release-id",
    "kolibri-v3-0123456789ab-abcdef012345",
    "--now-epoch",
    String(Date.parse("2026-07-30T18:30:00Z") / 1000),
  ];
  const scheduled = run("python3", scheduledArguments);
  requireSuccess(scheduled, "scheduled database backup");
  assert.match(scheduled.stdout, /database_scheduled_backup=ok/);
  const scheduledPath = path.join(
    scheduledRoot,
    "scheduled",
    "2026-07-30",
    "kolibri-v3-20260730T183000Z.db",
  );
  assert.equal((await stat(scheduledPath)).mode & 0o777, 0o600);
  const duplicateScheduled = run("python3", scheduledArguments);
  assert.equal(duplicateScheduled.status, 3);
  assert.match(duplicateScheduled.stderr, /output_already_exists/);

  const unsafeSource = path.join(canonicalRoot, "source-link.db");
  await symlink(source, unsafeSource);
  const rejected = run("python3", [
    helper,
    "verify",
    "--database",
    unsafeSource,
    "--expected-version",
    "43",
  ]);
  assert.equal(rejected.status, 3);
  assert.match(rejected.stderr, /database_recovery_error=database_path_unsafe/);
});

test("worker enablement requires exact endpoints and private credential files", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-enablement-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const canonicalRoot = await realpath(root);
  const credentials = path.join(canonicalRoot, "credentials");
  const workersEnvironment = path.join(canonicalRoot, "workers.env");
  await mkdir(credentials, { mode: 0o700 });
  await chmod(credentials, 0o700);
  for (const name of [
    "home-product-command-token",
    "home-product-identity-hmac-key",
    "provider-authority-command-token",
    "provider-authority-identity-hmac-key",
  ]) {
    await writeFile(path.join(credentials, name), "x".repeat(32), {
      mode: 0o600,
    });
    await chmod(path.join(credentials, name), 0o600);
  }
  await writeFile(
    workersEnvironment,
    [
      "KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL=http://127.0.0.1:39231/v1/product",
      "KOLIBRI_V3_HOME_PRODUCT_GOAL_COMMAND_URL=https://home.example/v1/goals",
      "KOLIBRI_V3_HOME_PRODUCT_PROVIDER_COMMAND_URL=https://home.example/v1/providers",
      "KOLIBRI_V3_PROVIDER_AUTHORITY_DISPATCH_CONFIGURED=true",
      "KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_URL=https://authority.example/v1/enroll",
      "",
    ].join("\n"),
    { mode: 0o600 },
  );
  await chmod(workersEnvironment, 0o600);

  for (const kind of ["product", "provider"]) {
    const result = run("python3", [
      path.join(PORTABLE_ROOT, "install-contract.py"),
      "validate-worker-enablement",
      "--kind",
      kind,
      "--workers-env",
      workersEnvironment,
      "--credentials-root",
      credentials,
      "--expected-uid",
      String(process.getuid()),
    ]);
    requireSuccess(result, `${kind} worker preflight`);
    assert.match(result.stdout, new RegExp(`worker_preflight=${kind}`));
  }

  await writeFile(
    workersEnvironment,
    "KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL=\n",
    { mode: 0o600 },
  );
  await chmod(workersEnvironment, 0o600);
  const rejected = run("python3", [
    path.join(PORTABLE_ROOT, "install-contract.py"),
    "validate-worker-enablement",
    "--kind",
    "product",
    "--workers-env",
    workersEnvironment,
    "--credentials-root",
    credentials,
    "--expected-uid",
    String(process.getuid()),
  ]);
  assert.equal(rejected.status, 3);
  assert.match(rejected.stderr, /worker_endpoint_missing/);
});

test("production installer rejects an operator-enabled embedded developer agent", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "kolibri-v3-backend-env-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const canonicalRoot = await realpath(root);
  const backendEnvironment = path.join(canonicalRoot, "backend.env");
  const helper = path.join(PORTABLE_ROOT, "install-contract.py");
  const commonArguments = [
    helper,
    "validate-operator-backend-env",
    "--backend-env",
    backendEnvironment,
    "--expected-uid",
    String(process.getuid()),
  ];

  await writeFile(
    backendEnvironment,
    "KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=true\n",
    { mode: 0o600 },
  );
  await chmod(backendEnvironment, 0o600);
  const forbidden = run("python3", commonArguments);
  assert.equal(forbidden.status, 3);
  assert.match(
    forbidden.stderr,
    /embedded_developer_agent_forbidden_in_production/,
  );

  await writeFile(
    backendEnvironment,
    [
      "KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=false",
      "KOLIBRI_V3_PROVIDER_EXECUTION_ENABLED=true",
      "",
    ].join("\n"),
    { mode: 0o600 },
  );
  await chmod(backendEnvironment, 0o600);
  const safe = run("python3", commonArguments);
  requireSuccess(safe, "safe operator backend environment");
  assert.match(
    safe.stdout,
    /operator_backend_environment=production_safe/,
  );
});

test("installer statically binds verification, immutable activation, health identity, and rollback", async () => {
  const installer = await readFile(
    path.join(PORTABLE_ROOT, "install.sh"),
    "utf8",
  );
  assert.doesNotMatch(installer, /source\s+"\$config_file"|source_digest/);
  assert.doesNotMatch(installer, /cat > "\$backend_env_file/);
  assert.doesNotMatch(
    installer,
    /KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=(?:true|false)/,
  );
  assert.match(installer, /--archive \/proc\/self\/fd\/7/);
  assert.match(installer, /--archive-name "\$release_archive_name"/);
  assert.match(installer, /--manifest \/proc\/self\/fd\/8/);
  assert.match(installer, /--checksum \/proc\/self\/fd\/6/);
  assert.match(installer, /installer_release_mismatch/);
  assert.match(installer, /post_build_verification/);
  assert.match(installer, /release_provenance_changed_during_build/);
  assert.match(installer, /ln -s [.]?[.]\/source\/backend/);
  assert.match(installer, /rm -rf -- "\$build_root"/);
  assert.match(installer, /find "\$release_stage" -type d -exec chmod 0555/);
  assert.match(installer, /mv -T "\$release_stage" "\$release_root"/);
  assert.match(installer, /KOLIBRI_RELEASE_ID=\$release_id/);
  assert.match(installer, /KOLIBRI_RELEASE_COMMIT=\$release_commit/);
  assert.match(
    installer,
    /KOLIBRI_V3_DIRECT_MODEL_RUNTIME=\$KOLIBRI_DIRECT_MODEL_RUNTIME/,
  );
  assert.match(installer, /KOLIBRI_V3_REQUIRE_PRODUCT_WORKER=true/);
  assert.match(installer, /install_error=product_worker_required/);
  assert.match(installer, /EnvironmentFile=\$backend_env_file[\s\S]+EnvironmentFile=\$release_env_file/);
  assert.match(installer, /UMask=0077/);
  assert.match(installer, /normalize-database/);
  assert.match(
    installer,
    /install -d -o root -g "\$service_group" -m 710 "\$KOLIBRI_BACKUP_ROOT"/,
  );
  assert.match(
    installer,
    /install -d -o "\$KOLIBRI_SERVICE_USER" -g "\$service_group" -m 700[\s\S]+"\$data_root" "\$scheduled_backup_root"/,
  );
  assert.match(
    installer,
    /database-rehearsal[.]py" backup[\s\S]+--source "\$data_root\/kolibri-v3[.]db"[\s\S]+--output "\$backup_dir\/kolibri-v3[.]db"/,
  );
  assert.match(installer, /"releaseId": sys[.]argv\[1\]/);
  assert.match(installer, /"releaseCommit": sys[.]argv\[2\]/);
  assert.match(installer, /KOLIBRI_ENABLE_PRODUCT_WORKER/);
  assert.match(installer, /validate-worker-enablement/);
  assert.match(installer, /validate-operator-backend-env/);
  assert.match(
    installer,
    /embedded_developer_agent_forbidden_in_production|validate_operator_backend_environment/,
  );
  assert.match(installer, /systemctl start "\$\{KOLIBRI_INSTANCE\}-product-run-worker[.]service"/);
  assert.ok(
    installer.indexOf(
      'systemctl start "${KOLIBRI_INSTANCE}-product-run-worker.service"',
    ) <
      installer.indexOf(
        '"http://127.0.0.1:$KOLIBRI_BACKEND_PORT/v1/ready"',
      ),
  );
  assert.match(installer, /systemctl enable "\$\{KOLIBRI_INSTANCE\}-provider-enrollment-worker[.]service"/);
  assert.match(installer, /restore_previous_durable_workers/);
  assert.match(installer, /restore_previous_monitor/);
  assert.match(installer, /restore_previous_backup_timer/);
  assert.match(installer, /release-monitor[.]service/);
  assert.match(installer, /database-backup[.]service/);
  assert.match(installer, /install_error=release_monitor_failed/);
  assert.ok(
    installer.indexOf(
      'systemctl start "${KOLIBRI_INSTANCE}-release-monitor.service"',
    ) < installer.lastIndexOf("switched=0"),
  );
  assert.match(installer, /product_worker=disabled_by_configuration|product_worker=\$product_worker_status/);
  assert.match(installer, /reconciliation_audit=installed_not_started/);
  assert.match(
    installer,
    /developer_execution=externalized_home_provider_worker_plane/,
  );
  assert.match(
    installer,
    /embedded_developer_agent=forbidden_in_production/,
  );
  assert.match(installer, /trusted_agent_plane=kolibri_agent_host/);
  assert.match(
    installer,
    /if \[\[ -f "\$backend_env_file[.]new" \]\]; then[\s\S]+mv -f "\$backend_env_file[.]new"/,
  );
});
