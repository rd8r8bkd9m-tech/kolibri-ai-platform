import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("mobile navigation opens the real bearer-backed account route", () => {
	const layout = read("app/_layout.tsx");
	const drawer = read("components/thread-list/drawer-content.tsx");
	const account = read("app/account.tsx");
	const session = read("src/auth/mobile-session.tsx");

	assert.match(layout, /<Drawer\.Screen\s+name="account"/);
	assert.match(drawer, /accessibilityLabel="Личный кабинет"/);
	assert.match(
		drawer,
		/navigation\.navigate\("account", \{ client: "mobile" \}\);\s*navigation\.closeDrawer\(\)/,
	);
	assert.match(account, /router\.replace\("\/app\?client=mobile"\)/);
	assert.match(account, /router\.push\("\/estimates\?client=mobile"\)/);

	assert.match(account, /useMobileSession\(\)/);
	assert.match(account, /session\.updateProfile\(\{ name: normalizedName \}\)/);
	assert.match(account, /session\.logout\(\)/);
	assert.doesNotMatch(account, /\bfetch\s*\(/);
	assert.doesNotMatch(account, /\/api\/v3/);

	assert.match(session, /authorizedFetch\(`\$\{API_BASE_URL\}\/v1\/profile`/);
	assert.match(session, /method: "PATCH"/);
	assert.match(session, /setUser\(updated\)/);
	assert.match(session, /\/v1\/mobile\/auth\/session/);
	assert.match(session, /refreshProfile/);
	assert.match(session, /navigator\?\.locks/);
	assert.match(session, /locks\.request\(REFRESH_TOKEN_LOCK, operation\)/);
	assert.match(
		session,
		/Platform\.OS === "web" \|\| typeof globalThis\.window !== "undefined"/,
	);
});

test("PWA billing uses hosted T-Bank checkout without leaking into native stores", () => {
	const account = read("app/account.tsx");
	const nativeBilling = read("components/settings/web-billing-settings.tsx");
	const webBilling = read("components/settings/web-billing-settings.web.tsx");
	const billingClient = read("src/billing/client.ts");
	const billingState = read("src/billing/use-web-billing-account.ts");

	assert.match(account, /Platform\.OS === "web" \? \(/);
	assert.match(account, /authorizedFetch=\{session\.authorizedFetch\}/);
	assert.match(account, /refreshProfile=\{session\.refreshProfile\}/);
	assert.match(account, /returnedIntent=\{returnedPaymentIntent\}/);
	assert.match(nativeBilling, /return null/);
	assert.doesNotMatch(
		nativeBilling,
		/\/v1\/billing|payment-intents|Т[‑-]Банк/,
	);

	assert.match(billingClient, /`\/v1\/billing\/payment-intents\/\$\{encodeURIComponent\(intentId\)\}`/);
	assert.match(billingClient, /"Idempotency-Key": idempotencyKey/);
	assert.match(billingClient, /returnSurface: "pwa"/);
	assert.match(billingClient, /\.hostname\.endsWith\("\.tbank\.ru"\)/);
	assert.doesNotMatch(billingClient, /\/api\/v3/);
	assert.match(billingState, /globalThis\.sessionStorage/);
	assert.match(billingState, /globalThis\.location\.assign\(nextPayment\.paymentUrl\)/);
	assert.match(billingState, /attempts >= 30/);
	assert.match(billingState, /2_000/);
	assert.match(webBilling, /Оплата пока не подключена/);
	assert.match(webBilling, /без автоматического продления/);
	assert.match(webBilling, /СБП \(QR\)/);
	assert.match(webBilling, /реквизиты не передаются Kolibri/);
	assert.doesNotMatch(
		`${billingClient}\n${billingState}\n${webBilling}`,
		/Recurrent|CustomerKey|RebillId|CardData|\bPAN\b|\bCVV\b/,
	);
});

test("mobile account is a reusable native settings surface, not a debug dashboard", () => {
	const account = read("app/account.tsx");
	const group = read("components/settings/settings-group.tsx");
	const row = read("components/settings/settings-row.tsx");
	const identity = read("components/settings/identity-summary.tsx");
	const editor = read("components/settings/profile-name-editor.tsx");

	assert.match(account, /<NativeScreenHeader[^>]+title="Личный кабинет"/);
	assert.match(account, /<ScrollView/);
	assert.match(account, /contentInsetAdjustmentBehavior="automatic"/);
	assert.match(account, /<SettingsGroup title="Аккаунт">/);
	assert.match(account, /<SettingsGroup title="Персонализация">/);
	assert.match(account, /<SettingsGroup title="Безопасность и доступ">/);
	assert.doesNotMatch(account, /user\.capabilities\.map/);
	assert.doesNotMatch(account, /user\.entitlements\.map/);

	assert.match(group, /colors\.surfaceRaised/);
	assert.match(row, /minHeight: 56/);
	assert.match(row, /haptics\.selection\(\)/);
	assert.match(identity, /profileInitials/);
	assert.match(editor, /canSave \|\| saving/);
	assert.match(editor, /accessibilityLiveRegion="polite"/);
});

test("mobile appearance preference is real, persistent, and platform-aware", () => {
	const provider = read("hooks/theme-provider.tsx");
	const layout = read("app/_layout.tsx");

	assert.match(provider, /type ThemePreference = "system" \| "light" \| "dark"/);
	assert.match(provider, /globalThis\.localStorage/);
	assert.match(provider, /SecureStore\.setItemAsync/);
	assert.match(provider, /setPreference/);
	assert.match(layout, /<KolibriThemeProvider>/);
	assert.match(layout, /<StatusBar style=\{isDark \? "light" : "dark"\}/);
});

test("closed mobile drawer is removed from assistive navigation", () => {
	const drawer = read("components/thread-list/drawer-content.tsx");

	assert.match(drawer, /accessibilityElementsHidden=\{!drawerOpen\}/);
	assert.match(drawer, /accessibilityViewIsModal=\{drawerOpen\}/);
	assert.match(drawer, /"no-hide-descendants"/);
});
