import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test, { afterEach } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const ROUTE_PATH = path.join(APP_ROOT, "app/api/health/route.ts");
const BACKEND_URL_HOOK = "__kolibriReleaseHealthBackendUrl";
const originalFetch = globalThis.fetch;
const originalReleaseId = process.env.KOLIBRI_RELEASE_ID;
const originalReleaseCommit = process.env.KOLIBRI_RELEASE_COMMIT;
const RELEASE_ID = "kolibri-v3-0123456789ab-abcdef012345";
const RELEASE_COMMIT = "0123456789abcdef0123456789abcdef01234567";

async function loadRoute() {
  const source = await readFile(ROUTE_PATH, "utf8");
  const injected = source.replace(
    /import\s+\{\s*v3BackendUrl\s*\}\s+from\s+["']@\/lib\/server\/v3-backend["'];/,
    `const v3BackendUrl = (pathname) => globalThis.${BACKEND_URL_HOOK}(pathname);`,
  );
  assert.notEqual(injected, source, "the backend URL import must be injectable");

  const executable = ts.transpileModule(injected, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ESNext,
    },
    fileName: ROUTE_PATH,
  }).outputText;
  return import(
    `data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`
  );
}

const route = await loadRoute();

afterEach(() => {
  globalThis.fetch = originalFetch;
  delete globalThis[BACKEND_URL_HOOK];
  if (originalReleaseId === undefined) {
    delete process.env.KOLIBRI_RELEASE_ID;
  } else {
    process.env.KOLIBRI_RELEASE_ID = originalReleaseId;
  }
  if (originalReleaseCommit === undefined) {
    delete process.env.KOLIBRI_RELEASE_COMMIT;
  } else {
    process.env.KOLIBRI_RELEASE_COMMIT = originalReleaseCommit;
  }
});

function installBackendUrl() {
  globalThis[BACKEND_URL_HOOK] = (pathname) => {
    assert.equal(pathname, "/v1/ready");
    return new URL("http://127.0.0.1:8002/v1/ready");
  };
}

function configureRelease() {
  process.env.KOLIBRI_RELEASE_ID = RELEASE_ID;
  process.env.KOLIBRI_RELEASE_COMMIT = RELEASE_COMMIT;
}

function backendHealth(overrides = {}) {
  return {
    status: "ok",
    service: "kolibri-v3",
    releaseId: process.env.KOLIBRI_RELEASE_ID,
    releaseCommit: process.env.KOLIBRI_RELEASE_COMMIT,
    ...overrides,
  };
}

test("GET reports the bounded release identity only after exact backend readiness", async () => {
  installBackendUrl();
  configureRelease();
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return Response.json(backendHealth());
  };

  const response = await route.GET();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.equal(response.headers.get("pragma"), "no-cache");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.deepEqual(await response.json(), {
    status: "ok",
    service: "kolibri-v3",
    releaseId: RELEASE_ID,
    releaseCommit: RELEASE_COMMIT,
  });
  assert.equal(request.url.href, "http://127.0.0.1:8002/v1/ready");
  assert.equal(request.options.method, "GET");
  assert.equal(request.options.cache, "no-store");
  assert.equal(request.options.redirect, "manual");
  assert.equal(request.options.headers.Accept, "application/json");
  assert.ok(request.options.signal instanceof AbortSignal);
});

test("HEAD performs the same readiness probe and never returns a body", async () => {
  installBackendUrl();
  delete process.env.KOLIBRI_RELEASE_ID;
  delete process.env.KOLIBRI_RELEASE_COMMIT;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return Response.json({ status: "ok", service: "kolibri-v3" });
  };

  const response = await route.HEAD();

  assert.equal(calls, 1);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.equal(await response.text(), "");
});

test("invalid, failed, malformed, and oversized upstream health all fail closed", async (t) => {
  const cases = [
    {
      name: "non-success HTTP",
      response: () =>
        Response.json(
          { status: "ok", service: "kolibri-v3" },
          { status: 500 },
        ),
    },
    {
      name: "wrong status",
      response: () =>
        Response.json({ status: "starting", service: "kolibri-v3" }),
    },
    {
      name: "wrong service",
      response: () =>
        Response.json({ status: "ok", service: "another-service" }),
    },
    {
      name: "malformed JSON",
      response: () => new Response("{not-json"),
    },
    {
      name: "oversized body",
      response: () => new Response(`{"padding":"${"x".repeat(4_096)}"}`),
    },
  ];

  for (const scenario of cases) {
    await t.test(scenario.name, async () => {
      installBackendUrl();
      configureRelease();
      globalThis.fetch = async () => scenario.response();

      const response = await route.GET();

      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), {
        status: "unavailable",
        service: "kolibri-v3",
        releaseId: RELEASE_ID,
        releaseCommit: RELEASE_COMMIT,
        code: "backend_not_ready",
      });
    });
  }
});

test("configuration and network errors expose neither exceptions nor backend URLs", async () => {
  globalThis[BACKEND_URL_HOOK] = () => {
    throw new Error(
      "credential=do-not-expose url=https://internal.example.invalid",
    );
  };
  process.env.KOLIBRI_RELEASE_ID =
    "unsafe\nrelease=https://secret.example.invalid";
  globalThis.fetch = async () => {
    throw new Error("token=also-do-not-expose");
  };

  const response = await route.GET();
  const body = await response.text();

  assert.equal(response.status, 503);
  assert.deepEqual(JSON.parse(body), {
    status: "unavailable",
    service: "kolibri-v3",
    releaseId: "unversioned",
    code: "backend_not_ready",
  });
  assert.doesNotMatch(body, /credential|token|internal\.example|secret\.example/i);
});

test("release identity accepts at most 128 safe characters", async () => {
  installBackendUrl();
  process.env.KOLIBRI_RELEASE_COMMIT = RELEASE_COMMIT;
  globalThis.fetch = async () => Response.json(backendHealth());

  process.env.KOLIBRI_RELEASE_ID = `r${"a".repeat(127)}`;
  const accepted = await route.GET();
  assert.equal(accepted.status, 200);
  assert.equal((await accepted.json()).releaseId.length, 128);

  process.env.KOLIBRI_RELEASE_ID = `r${"a".repeat(128)}`;
  const rejected = await route.GET();
  assert.equal(rejected.status, 503);
  assert.equal((await rejected.json()).releaseId, "unversioned");
});

test("release provenance exposes only an exact lowercase Git commit", async () => {
  installBackendUrl();
  globalThis.fetch = async () => Response.json(backendHealth());
  process.env.KOLIBRI_RELEASE_ID = "kolibri-v3-release";
  process.env.KOLIBRI_RELEASE_COMMIT = RELEASE_COMMIT;

  assert.deepEqual(await (await route.GET()).json(), {
    status: "ok",
    service: "kolibri-v3",
    releaseId: "kolibri-v3-release",
    releaseCommit: RELEASE_COMMIT,
  });

  for (const invalid of [
    "0123456789ABCDEF0123456789ABCDEF01234567",
    "0123456789abcdef0123456789abcdef0123456",
    "0123456789abcdef0123456789abcdef012345678",
    "0123456789abcdef0123456789abcdef01234567\nsecret",
  ]) {
    process.env.KOLIBRI_RELEASE_COMMIT = invalid;
    const response = await route.GET();
    assert.equal(response.status, 503);
    const payload = await response.json();
    assert.equal("releaseCommit" in payload, false);
    assert.doesNotMatch(JSON.stringify(payload), /secret|ABCDEF/);
  }
});

test("frontend rejects a healthy backend from a different release", async (t) => {
  const cases = [
    {
      name: "release ID mismatch",
      health: () =>
        backendHealth({
          releaseId: "kolibri-v3-aaaaaaaaaaaa-bbbbbbbbbbbb",
        }),
    },
    {
      name: "release commit mismatch",
      health: () =>
        backendHealth({
          releaseCommit: "a".repeat(40),
        }),
    },
    {
      name: "missing backend provenance",
      health: () => ({ status: "ok", service: "kolibri-v3" }),
    },
  ];

  for (const scenario of cases) {
    await t.test(scenario.name, async () => {
      installBackendUrl();
      configureRelease();
      globalThis.fetch = async () => Response.json(scenario.health());

      const response = await route.GET();

      assert.equal(response.status, 503);
      assert.equal((await response.json()).code, "backend_not_ready");
    });
  }
});
