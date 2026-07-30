import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  isProviderId,
  PROVIDER_IDS,
} from "../lib/provider-connections.ts";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

test("provider settings submit credentials only through bounded same-origin routes", async () => {
  const [
    profile,
    client,
    statusRoute,
    enrollmentRoute,
    mimoCredentialRoute,
    codexLoginRoute,
    backend,
    security,
  ] =
    await Promise.all([
      readSource("components/kolibri-shell/profile-settings-surface.tsx"),
      readSource("lib/providers/client.ts"),
      readSource("app/api/superadmin/provider-connections/route.ts"),
      readSource(
        "app/api/superadmin/provider-connections/[providerId]/enrollments/route.ts",
      ),
      readSource(
        "app/api/superadmin/provider-connections/mimo-code/credential/route.ts",
      ),
      readSource(
        "app/api/superadmin/provider-connections/codex-cli/login-status/route.ts",
      ),
      readSource("backend/app/provider_connections.py"),
      readSource("backend/app/security.py"),
    ]);

  const aiModelsSection = profile.slice(
    profile.indexOf("function AiModelsSection"),
    profile.indexOf("function SecuritySection"),
  );
  assert.match(
    aiModelsSection,
    /const\s+isSuperadmin\s*=\s*user\.isPlatformOwner/,
  );
  assert.match(aiModelsSection, /\bconnectMimo\b/);
  assert.match(aiModelsSection, /\bconnectCodexLogin\b/);
  assert.match(aiModelsSection, /\bstartProviderEnrollment\b/);
  assert.match(aiModelsSection, /\bcreateProviderEnrollmentNonce\b/);
  assert.match(aiModelsSection, /\bLOCAL_PROVIDER_CONNECTIONS_ENABLED\b/);
  assert.match(aiModelsSection, /type\s*=\s*["']password["']/i);
  assert.match(aiModelsSection, /autoComplete=["']off["']/);
  assert.match(aiModelsSection, /setMimoKey\(["']["']\)/);

  assert.match(client, /body:\s*JSON\.stringify\(\{\s*apiKey\s*\}\)/);
  assert.match(client, /credentials:\s*["']same-origin["']/);
  assert.match(
    client,
    /LOCAL_PROVIDER_CONNECTIONS_ENABLED\s*=\s*\n?\s*process\.env\.NODE_ENV\s*===\s*["']development["']/,
  );
  assert.equal(
    (client.match(/if\s*\(!LOCAL_PROVIDER_CONNECTIONS_ENABLED\)/g) ?? [])
      .length,
    2,
    "both direct credential clients must fail closed outside development",
  );
  assert.match(
    client,
    /`\/api\/superadmin\/provider-connections\/\$\{providerId\}\/enrollments`/,
  );
  assert.match(client, /["']Idempotency-Key["']:\s*idempotencyNonce/);
  assert.doesNotMatch(client, /\blocalStorage\b|\bsessionStorage\b/);

  assert.match(statusRoute, /\bproxyV3JsonRequest\b/);
  assert.match(statusRoute, /["']\/v1\/provider-connections["']/);
  assert.match(enrollmentRoute, /\bisProviderId\b/);
  assert.match(enrollmentRoute, /\bproxyV3JsonRequest\b/);
  assert.match(
    enrollmentRoute,
    /`\/v1\/provider-connections\/\$\{providerId\}\/enrollment-intents`/,
  );
  const bff = `${statusRoute}\n${enrollmentRoute}`;
  assert.doesNotMatch(bff, /KOLIBRI_PROVIDER_AUTHORITY/);
  assert.doesNotMatch(bff, /\bAuthorization\b|\bserviceToken\b/);
  assert.doesNotMatch(bff, /providerEnrollmentAuthorityUrl/);
  assert.match(mimoCredentialRoute, /maxRequestBytes:\s*12\s*\*\s*1_024/);
  assert.match(codexLoginRoute, /maxRequestBytes:\s*0/);

  assert.match(backend, /\bDepends\(require_owner\)/);
  assert.match(backend, /\bDepends\(require_mutation_auth\)/);
  assert.match(
    security,
    /def require_mutation_auth[\s\S]*?require_bearer_session[\s\S]*?require_same_origin[\s\S]*?require_csrf/,
  );
  assert.match(backend, /provider_enrollment_reauthentication_required/);
  assert.match(backend, /Provider credentials and request payloads are not accepted/);
  assert.match(backend, /@router\.post\(["']\/mimo-code\/credential["']\)/);
  assert.match(backend, /@router\.post\(["']\/codex-cli\/login-status["']\)/);
  assert.match(backend, /owner_authorization_decision_id/);
  assert.match(backend, /command_json/);
  assert.doesNotMatch(backend, /authorizationUrl|authorization_url/);
});

test("successful provider actions refresh the shared model catalog without stale overwrites", async () => {
  const [profile, modelProvider] = await Promise.all([
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("lib/models/provider.tsx"),
  ]);
  const aiModelsSection = profile.slice(
    profile.indexOf("function AiModelsSection"),
    profile.indexOf("function SecuritySection"),
  );

  assert.match(aiModelsSection, /\buseModelCatalog\(\)/);
  assert.match(
    aiModelsSection,
    /const\s+enrollment\s*=\s*await\s+startProviderEnrollment\(/,
  );
  assert.match(
    aiModelsSection,
    /const\s+refreshed\s*=\s*await\s+load\(\);\s*if\s*\(refreshed\)\s*\{\s*await\s+modelCatalog\.refresh\(\)/,
  );
  assert.equal(
    (aiModelsSection.match(/await\s+modelCatalog\.refresh\(\)/g) ?? [])
      .length,
    3,
    "local connect, durable enrollment, and manual refresh must each reload the catalog",
  );

  assert.match(modelProvider, /\brequestVersionRef\s*=\s*useRef\(0\)/);
  assert.match(
    modelProvider,
    /requestVersionRef\.current\s*!==\s*requestVersion/,
  );
  assert.match(
    modelProvider,
    /if\s*\(requestVersionRef\.current\s*===\s*requestVersion\)/,
  );
});

test("the BFF accepts only the two fixed provider route segments", () => {
  assert.deepEqual(PROVIDER_IDS, ["mimo-code", "codex-cli"]);
  assert.equal(isProviderId("mimo-code"), true);
  assert.equal(isProviderId("codex-cli"), true);
  assert.equal(isProviderId("../primary"), false);
  assert.equal(isProviderId("https://attacker.example"), false);
});

test("obsolete direct provider proxy routes and verifier are absent", async () => {
  for (const relativePath of [
    "app/api/v3/providers/route.ts",
    "app/api/v3/providers/mimo-code/credential/route.ts",
    "app/api/v3/providers/codex-cli/device-login/route.ts",
    "app/api/v3/providers/[providerId]/probe/route.ts",
    "lib/server/v3-superadmin.ts",
  ]) {
    await assert.rejects(access(path.join(APP_ROOT, relativePath)));
  }
});
