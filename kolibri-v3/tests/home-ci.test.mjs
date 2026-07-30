import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function read(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const dockerfile = read("../deploy/home-ci/Dockerfile");
const rustDockerfile = read("../deploy/home-ci/Dockerfile.rust");
const gate = read("../deploy/home-ci/gate-inside-container.sh");
const hostGate = read("../deploy/home-ci/run-gate.sh");
const runner = read("../deploy/home-ci/runner.sh");
const receiver = read("../deploy/home-ci/post-receive");
const installer = read("../deploy/home-ci/install.sh");

test("Home CI pins the R1 toolchains and never mounts Docker or production", () => {
  assert.match(dockerfile, /node:24[.]18[.]0-bookworm/);
  assert.match(dockerfile, /python:3[.]12[.]13-bookworm/);
  assert.match(rustDockerfile, /rust:1[.]85[.]0-bookworm/);
  assert.match(rustDockerfile, /RUSTUP_VERSION=1[.]28[.]2/);
  assert.match(rustDockerfile, /sha256sum --check --strict/);
  assert.match(rustDockerfile, /--component rustfmt,clippy/);
  assert.match(hostGate, /Dockerfile[.]rust/);
  assert.match(hostGate, /rust185-/);
  assert.doesNotMatch(hostGate, /docker[.]sock/);
  assert.doesNotMatch(hostGate, /\/etc\/kolibri|\/var\/lib\/kolibri/);
  assert.match(hostGate, /--pids-limit/);
  assert.match(hostGate, /--memory/);
});

test("Home CI runs the complete exact-commit R1 product gate", () => {
  assert.match(gate, /actual_commit.*expected_commit/s);
  assert.match(gate, /candidate_not_clean/);
  assert.match(gate, /cache_root=.*[.]home-ci/);
  assert.match(gate, /export HOME=/);
  assert.match(gate, /export NPM_CONFIG_CACHE=/);
  assert.match(gate, /npm audit --audit-level=high/);
  assert.match(gate, /npm run typecheck/);
  assert.match(gate, /npm test/);
  assert.match(gate, /npm run build/);
  assert.match(gate, /pytest -q backend\/tests/);
  assert.match(gate, /server\/validate_contracts[.]py/);
  assert.match(gate, /expo-doctor@1[.]20[.]1/);
  assert.match(gate, /npm run export:ios/);
  assert.match(gate, /npm run export:android/);
  assert.match(gate, /systemd-analyze verify/);
  assert.match(gate, /build-release[.]sh/);
  assert.match(gate, /smoke-test[.]sh/);
  assert.match(hostGate, /cargo fmt --check/);
  assert.match(hostGate, /cargo test --locked/);
  assert.match(hostGate, /cargo clippy --locked --all-targets/);
});

test("Home receiver queues only fast-forward candidate commits", () => {
  assert.match(receiver, /refs\/heads\/candidate/);
  assert.match(receiver, /\^\[0-9a-f\]\{40\}\$/);
  assert.match(installer, /receive[.]denyNonFastforwards true/);
  assert.match(installer, /receive[.]denyDeletes true/);
  assert.match(installer, /systemctl --user enable --now/);
  assert.match(runner, /git clone --no-local --no-checkout/);
  assert.match(runner, /checkout --detach/);
  assert.match(runner, /rm -rf -- "\$\{worktree\}"/);
});
