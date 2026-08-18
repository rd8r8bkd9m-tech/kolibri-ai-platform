import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

const read = (relativePath) =>
	readFileSync(new URL(`../${relativePath}`, import.meta.url), "utf8");

test("the ChatGPT-inspired development plan exists without legacy gates", () => {
	const plan = read("../../docs/MOBILE_CHATGPT_DEVELOPMENT_PLAN.md");

	assert.match(plan, /# План разработки мобильного клиента Kolibri/);
	assert.match(plan, /Фаза 1 — Shell, header и сайдбар/);
	assert.match(plan, /Фаза 2 — Composer и ввод/);
	assert.match(plan, /Фаза 3 — Сообщения, стриминг и результаты/);
	assert.match(plan, /Фаза 4 — Проекты, библиотека, удалённые источники/);
	assert.match(plan, /Фаза 5 — Тема, жесты, доступность/);
	assert.match(plan, /Фаза 6 — QA и финальная проверка/);
	assert.doesNotMatch(plan, /npm run (verify|typecheck|lint)/);
	assert.doesNotMatch(plan, /expo-doctor/);
	assert.doesNotMatch(plan, /export:ios|export:android/);
});

test("mobile header follows the empty/active ChatGPT reference states", () => {
	const header = read("components/shell/mobile-header.tsx");
	const theme = read("constants/theme.ts");

	assert.match(header, /isEmpty = useAuiState/);
	assert.match(header, /accessibilityLabel="Обновить"/);
	assert.match(header, /accessibilityLabel="История"/);
	assert.match(header, /name="history"/);
	assert.match(header, /aui\.threads\.reload\(\)/);
	assert.match(header, /actionCapsule/);
	assert.match(header, /aui\.threads\.item\("main"\)\.rename\(next\)/);
	assert.match(header, /promptAsync/);
	assert.match(header, /accessibilityLabel="Ещё действия"/);
	assert.match(theme, /headerControl: 40/);
	assert.match(theme, /composerInset: 18/);
});

test("composer is a single-row ChatGPT capsule with real send/stop and voice controls", () => {
	const composer = read("components/assistant-ui/composer/index.tsx");
	const controls = read("components/assistant-ui/composer/controls.tsx");
	const composerStyles = read("components/assistant-ui/composer/styles.ts");

	assert.match(composerStyles, /flexDirection: "row",/);
	assert.match(composerStyles, /minHeight: 40,/);
	assert.match(composer, /<MicButton \/>/);
	assert.match(composer, /<VoiceButton \/>/);
	assert.match(controls, /startDictation\(\)/);
	assert.match(controls, /useVoiceControls/);
	assert.match(controls, /useAuiState\([\s\S]*capabilities\.dictation/);
	assert.match(controls, /useAuiState\([\s\S]*capabilities\.voice/);
	assert.match(controls, /stopSquare/);
	assert.match(composerStyles, /send: \{/);
	assert.match(composerStyles, /borderRadius: Radius\.control,\n\t\theight: 46,/);
});

test("drawer exposes reference destinations, search and settings", () => {
	const drawer = read("src/components/overlays/Sidebar.tsx");

	assert.match(drawer, /visibleMenu\.map/);
	assert.match(drawer, /accessibilityLabel=\{COPY\.searchLabel\}/);
	assert.match(drawer, /pinnedRows/);
	assert.match(drawer, /recentRows/);
	assert.match(drawer, /navigate\("\/account\?client=mobile"\)/);
	assert.match(drawer, /accessibilityLabel=\{COPY\.settingsLabel\}/);
});

test("projects/library/remote routes are registered and server-backed or honest", () => {
	const layout = read("app/_layout.tsx");
	const projects = read("app/projects.tsx");
	const library = read("app/library.tsx");
	const remote = read("app/remote.tsx");

	assert.ok(existsSync(new URL("../app/projects.tsx", import.meta.url)));
	assert.match(layout, /<Drawer\.Screen\s+name="projects"/);
	assert.match(layout, /<Drawer\.Screen\s+name="library"/);
	assert.match(layout, /<Drawer\.Screen\s+name="remote"/);
	assert.match(projects, /new ProductChatClient/);
	assert.match(projects, /listThreads\(\)/);
	assert.match(projects, /SurfaceBoundary/);
	assert.match(library, /title="Документы"/);
	assert.match(library, /DocumentsClient/);
	assert.match(remote, /title="Удаленно"/);
	assert.match(remote, /SurfaceBoundary/);
});

test("AG-UI data cards render through a compile-time allowlist with fallback", () => {
	const message = read("components/assistant-ui/message.tsx");
	const cards = read("src/product-chat/cards.ts");
	const fallback = read("components/assistant-ui/cards/data-card-fallback.tsx");

	assert.match(message, /DATA_PART_NAMES\.weather/);
	assert.match(message, /DATA_PART_NAMES\.imageGeneration/);
	assert.match(message, /Fallback:/);
	assert.match(cards, /DATA_PART_NAMES/);
	assert.match(cards, /parseWeatherCard/);
	assert.match(cards, /parseImageGenerationCard/);
	assert.match(fallback, /Неподдерживаемый тип данных/);
});

test("theme applies before hydration on web and long-press is 250ms", () => {
	const provider = read("hooks/theme-provider.tsx");
	const item = read("src/components/ui/ListItem.tsx");

	assert.match(provider, /readStoredPreferenceSync/);
	assert.match(provider, /useState<ThemePreference>\(\(\) =>\s*readStoredPreferenceSync\(\)/);
	assert.match(item, /delayLongPress=\{250\}/);
});
