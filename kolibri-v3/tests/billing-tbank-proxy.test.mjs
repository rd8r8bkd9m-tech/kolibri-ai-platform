import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const read = (relative) =>
  fs.readFileSync(path.join(root, relative), "utf8");

test("billing BFF exposes only the canonical bounded V3 routes", () => {
  const routes = {
    plans: read("app/api/v3/billing/plans/route.ts"),
    create: read("app/api/v3/billing/payment-intents/route.ts"),
    payment: read(
      "app/api/v3/billing/payment-intents/[intentId]/route.ts",
    ),
    subscriptions: read("app/api/v3/billing/subscriptions/route.ts"),
    notification: read(
      "app/api/v3/billing/tbank/notifications/route.ts",
    ),
    paymentReturn: read(
      "app/api/v3/billing/tbank/return/[intentId]/route.ts",
    ),
  };
  const combined = Object.values(routes).join("\n");

  assert.match(routes.plans, /["']\/v1\/billing\/plans["']/);
  assert.match(
    routes.create,
    /["']\/v1\/billing\/payment-intents["']/,
  );
  assert.match(routes.create, /maxRequestBytes:\s*4\s*\*\s*1_024/);
  assert.match(
    routes.payment,
    /\/v1\/billing\/payment-intents\/\$\{encodeURIComponent\(intentId\)\}/,
  );
  assert.match(
    routes.subscriptions,
    /["']\/v1\/billing\/subscriptions["']/,
  );
  assert.match(
    routes.notification,
    /["']\/v1\/billing\/tbank\/notifications["']/,
  );
  assert.match(
    routes.notification,
    /maxRequestBytes:\s*64\s*\*\s*1_024/,
  );
  assert.doesNotMatch(
    routes.notification,
    /require_mutation_auth|x-csrf-token|JSON\.(?:parse|stringify)/,
  );
  assert.match(routes.paymentReturn, /SAFE_NONCE/);
  assert.match(routes.paymentReturn, /providerResult/);
	assert.match(routes.paymentReturn, /status:\s*303/);
	assert.match(routes.paymentReturn, /account:\s*"billing"/);
	assert.match(routes.paymentReturn, /returnSurface/);
	assert.match(routes.paymentReturn, /destinationPath\s*=\s*returnSurface/);
	assert.match(routes.paymentReturn, /Location:\s*`\$\{destinationPath\}\?/);
	assert.doesNotMatch(routes.paymentReturn, /new URL\([^)]*request\.url/);
	assert.match(routes.paymentReturn, /fetchV3Backend/);
  assert.match(combined, /proxyV3JsonRequest/);
  assert.doesNotMatch(
    combined,
    /KOLIBRI_V3_TBANK_(?:PASSWORD|TERMINAL_KEY)|CardData|\bPAN\b|\bCVV\b/,
  );
});

test("billing account UI follows the server-backed hosted checkout", () => {
	const client = read("lib/billing/client.ts");
	const state = read("lib/billing/use-billing-account.ts");
	const section = read("components/billing/billing-account-section.tsx");
	const profile = read("components/kolibri-shell/profile-settings-surface.tsx");
	const workspace = read(
		"components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
	);

	assert.match(client, /["']Idempotency-Key["']/);
	assert.match(client, /paymentUrl/);
	assert.match(state, /sessionStorage/);
	assert.match(state, /window\.location\.assign\(nextPayment\.paymentUrl\)/);
	assert.match(state, /getBillingPayment/);
	assert.match(section, /Оплата пока не подключена/);
	assert.match(section, /без автоматического продления/);
	assert.match(section, /Данные карты не\s+передаются Kolibri/);
	assert.match(profile, /<BillingAccountSection\s*\/>/);
	assert.match(workspace, /destination\s*===\s*["']billing["']/);
	assert.doesNotMatch(
		`${client}\n${state}\n${section}`,
		/Recurrent|CustomerKey|RebillId|CardData|\bPAN\b|\bCVV\b/,
	);
});

test("shared BFF preserves raw body and signed webhook content type", () => {
  const helper = read("lib/server/v3-backend.ts");

  assert.match(helper, /["']content-type["']/);
  assert.match(helper, /request\.arrayBuffer\(\)/);
  assert.match(helper, /body\.byteLength\s*>\s*maxBytes/);
  assert.doesNotMatch(helper, /JSON\.parse\(.*request|request\.json\(\)/s);
});
