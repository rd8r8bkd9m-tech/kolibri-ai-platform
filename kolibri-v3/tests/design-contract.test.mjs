import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

const readSources = async (relativePaths) =>
	(await Promise.all(relativePaths.map(readSource))).join("\n");

async function collectSourceFiles(relativeDirectory) {
  const directory = path.join(APP_ROOT, relativeDirectory);
  const entries = await readdir(directory, { withFileTypes: true });
  const sources = [];

  for (const entry of entries) {
    const relativePath = path.join(relativeDirectory, entry.name);

    if (entry.isDirectory()) {
      sources.push(...(await collectSourceFiles(relativePath)));
      continue;
    }

    if (/\.[cm]?[jt]sx?$/.test(entry.name)) {
      sources.push(relativePath);
    }
  }

  return sources;
}

test("the welcome surface uses four desktop and three mobile assistant-ui prompts", async () => {
  const thread = await readSources([
    "components/assistant-ui/thread/layouts/thread-screen.tsx",
    "components/assistant-ui/thread/parts/thread-layout.tsx",
    "components/assistant-ui/thread/thread-suggestions-config.ts",
  ]);

  assert.match(thread, /\bKolibri\b/i);

  assert.match(thread, /MOBILE_STARTERS\.map/);
  assert.match(thread, /(?:desktopStarters|DESKTOP_STARTERS)\.map/);
  assert.equal((thread.match(/<ThreadPrimitive\.Suggestion\b/g) ?? []).length, 2);
  assert.equal((thread.match(/\bprompt=\{prompt\}/g) ?? []).length, 2);

  for (const title of [
    "Рассчитать смету",
    "Спланировать проект",
    "Подготовить документ",
    "Проверить основания",
  ]) {
    assert.ok(thread.includes(title), `missing starter prompt: ${title}`);
  }

  for (const title of [
    "Создать изображение",
    "Напиши или отредактируй",
    "Искать в интернете",
  ]) {
    assert.ok(thread.includes(title), `missing mobile action: ${title}`);
  }
});

test("the compact shell matches the mobile chat contract and persists theme choice", async () => {
  const [
    shell,
    header,
    sidebar,
    sidebarControls,
    sidebarBrand,
    sidebarProfileFooter,
    sidebarNavigation,
    thread,
    threadList,
    theme,
    layout,
    css,
    runtimeProvider,
  ] = await Promise.all([
    readSources([
      "components/kolibri-shell/desktop-workspace/desktop-workspace.tsx",
      "components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx",
      "components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
    ]),
    readSource("components/kolibri-shell/mobile-workspace-header.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/sidebar/sidebar-controls.tsx"),
    readSource("components/kolibri-shell/sidebar/sidebar-brand.tsx"),
    readSource("components/kolibri-shell/sidebar/workspace-sidebar-profile-footer.tsx"),
    readSource("components/kolibri-shell/sidebar/workspace-sidebar-navigation.tsx"),
    readSources([
      "components/assistant-ui/thread/layouts/thread-screen.tsx",
      "components/assistant-ui/thread/parts/thread-layout.tsx",
      "components/assistant-ui/thread/parts/thread-message.tsx",
      "components/assistant-ui/thread/parts/thread-message-primitives.tsx",
      "components/assistant-ui/thread/thread-shell.tsx",
      "components/assistant-ui/thread/thread-ui-constants.ts",
      "components/ui/class-names.ts",
    ]),
    readSources([
      "components/assistant-ui/thread-list/thread-list-core.tsx",
      "components/assistant-ui/thread-list/thread-list-item.tsx",
      "components/assistant-ui/thread-list/thread-list-utils.ts",
    ]),
    readSource("components/theme/kolibri-theme-provider.tsx"),
    readSources(["app/app/layout.tsx", "app/layout.tsx"]),
    readSource("app/globals.css"),
    readSource("app/MyRuntimeProvider.tsx"),
  ]);

  assert.match(shell, /<DesktopWorkspaceLayout\b/);
  assert.match(shell, /<WorkspaceHeader\b/);
  assert.match(shell, /<Thread\b/);
  assert.match(shell, /navigationOpen/);
  assert.match(header, /<ThreadListPrimitive\.New\b/);
  assert.match(header, /Открыть меню/);
  assert.match(header, /aria-expanded=\{navigationOpen\}/);
  assert.match(shell, /navigationOpen=\{navigationOpen\}/);
  assert.match(header, /data-slot=["']mobile-hamburger-icon["']/);
  assert.match(header, /data-slot=["']mobile-editor-back["']/);
  assert.match(header, /aria-label=["']На основной экран["']/);
  assert.match(
    sidebar,
    /data-overlay=\{isOverlay\s*\?\s*["']true["']\s*:\s*["']false["']\}/,
  );
  assert.match(
    sidebarBrand,
    /data-slot=["']workspace-sidebar-brand["'][\s\S]{0,240}Колибри/,
  );
  assert.match(sidebarNavigation, /data-slot=["']workspace-sidebar-body["']/);
  assert.match(sidebarNavigation, /isOverlay/);
  assert.match(sidebarControls, /data-canvas-launcher=\{normalizedLauncherId\}/);
  assert.match(sidebarProfileFooter, /data-slot=["']workspace-profile-footer["']/);
  assert.match(shell, /aria-label=["']Диалог с Kolibri["']/);
  assert.match(shell, /inert=\{chatHidden\s*\?/);
  assert.match(shell, /id=["']auxiliary-canvas["']/);
  assert.equal(
    (header.match(/uiClassTokens\.mobileHeaderHamburgerBar/g) ?? [])
      .length,
    2,
  );
  assert.match(header, /aria-label=\{`\$\{CHAT_DESTINATION_LABEL\}\. Выбрать раздел`\}/);
  assert.match(header, /CHAT_DESTINATION_LABEL/);
  assert.match(header, /onOpenDestination/);
  assert.doesNotMatch(header, /AgentProfileSelector/);
  assert.match(thread, /aui-composer-mobile-model/);
  assert.match(thread, /data-mobile-layout=\{compact\s*\?/);
  assert.match(thread, /aui-mobile-starter-actions/);
  assert.match(thread, /Спросить Chat\.\.\./);
  assert.match(threadList, /setTimeout\(\(\)\s*=>\s*\{/);
  assert.match(threadList, /setMenuOpen\(true\)/);
  assert.match(threadList, /onContextMenu=/);
  assert.match(threadList, /COMPACT_THREAD_MENU_QUERY\s*=\s*["']\(max-width:\s*959px\)["']/);
  assert.match(threadList, /data-long-pressing=\{longPressing\s*\?/);
  assert.match(threadList, /data-thread-long-press-consumed/);
  assert.match(
    threadList,
    /onClickCapture=\{preventConsumedLongPressNavigation\}/,
  );
  assert.match(threadList, /canStartThreadLongPress\(\{[\s\S]{0,100}\bisDraft\b/);
  assert.match(
    threadList,
    /if\s*\(isDraft\)\s*\{[\s\S]{0,80}event\.preventDefault\(\)[\s\S]{0,40}return/,
  );
  assert.match(threadList, /navigator\.vibrate\?\.\(10\)/);
  assert.match(threadList, /side=\{compactThreadMenu\s*\?\s*["']bottom["']\s*:\s*["']right["']\}/);
  assert.match(sidebarNavigation, /shouldCloseThreadDrawerForClick/);
  assert.match(css, /\[data-slot=["']workspace-file-category-tabs["']\]/);
  assert.doesNotMatch(css, /\.border-border\\\/80\.flex\.gap-1/);
  assert.match(theme, /KOLIBRI_THEME_STORAGE_KEY\s*=\s*["']kolibri-theme["']/);
  assert.match(theme, /prefers-color-scheme:\s*dark/);
  assert.match(layout, /<KolibriThemeProvider\b/);
  assert.doesNotMatch(layout, /dangerouslySetInnerHTML/);
  assert.match(css, /@media\s*\(max-width:\s*959px\)/);
  assert.match(css, /--background:\s*#000000/);
  assert.match(css, /--background:\s*#ffffff/);
  assert.match(css, /-webkit-touch-callout:\s*none/);
  assert.match(css, /touch-action:\s*pan-y/);
  assert.doesNotMatch(thread, /aui-composer-voice-submit-icon/);
  assert.match(thread, /composerEmpty\s*\|\|/);
  assert.match(thread, /Голосовой ввод недоступен/);
  assert.match(
    runtimeProvider,
    /WebSpeechDictationAdapter\.isSupported\(\)/,
  );
  assert.match(runtimeProvider, /language:\s*["']ru-RU["']/);
  assert.match(runtimeProvider, /\bdictation,\s*\n\s*feedback:/);
});

test("mobile runtime uses iOS and Android viewport primitives", async () => {
  const [environment, layout, css] = await Promise.all([
    readSource("components/kolibri-shell/mobile-environment.tsx"),
    readSources(["app/app/layout.tsx", "app/layout.tsx"]),
    readSource("app/globals.css"),
  ]);

  assert.match(layout, /viewportFit:\s*["']cover["']/);
  assert.match(layout, /interactiveWidget:\s*["']resizes-content["']/);
  assert.match(layout, /appleWebApp:/);
  assert.match(layout, /<MobileEnvironment\s*\/>/);
  assert.match(environment, /window\.visualViewport/);
  assert.match(environment, /iPhone\|iPad\|iPod/);
  assert.match(environment, /Android/);
  assert.match(environment, /--kolibri-visual-viewport-height/);
  assert.match(environment, /virtualKeyboard/);
  assert.match(environment, /--kolibri-visual-viewport-offset-top/);
  assert.match(css, /var\(--kolibri-visual-viewport-height,\s*100dvh\)/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
});

test("the estimate editor uses mobile cards without changing desktop table behavior", async () => {
  const editor = await readSources([
    "components/assistant-ui/product-widgets/estimate-editor.tsx",
    "components/assistant-ui/product-widgets/estimate-document-card.tsx",
  ]);

  assert.match(editor, /data-slot=["']estimate-mobile-list["']/);
  assert.match(editor, /matchMedia\(["']\(max-width:\s*959px\)["']\)/);
  assert.match(editor, /\bopenEstimateInWorkspace\(/);
  assert.match(editor, /\bmin-\[960px\]:hidden\b/);
  assert.match(
    editor,
    /\bhidden overflow-x-auto min-\[960px\]:block\b/,
  );
  assert.match(editor, /inputMode=["']decimal["']/);
  assert.match(editor, /enterKeyHint=["']done["']/);
  assert.match(editor, /env\(safe-area-inset-bottom\)/);
  assert.match(editor, /<SupplierOfferForm\b/);
});

test("the visible weather scene does not lazy-load its LCP backdrop", async () => {
  const widgets = await readSource(
    "components/assistant-ui/product-widgets/weather.tsx",
  );

  assert.match(
    widgets,
    /kolibri-weather-scene__backdrop[\s\S]{0,220}loading=["']eager["']/,
  );
});

test("profile settings expose all persisted appearance modes", async () => {
  const profile = await readSource(
    "components/kolibri-shell/profile-settings-surface.tsx",
  );

  assert.match(profile, /label:\s*["']Системная["']/);
  assert.match(profile, /label:\s*["']Светлая["']/);
  assert.match(profile, /label:\s*["']Тёмная["']/);
  assert.match(profile, /onClick=\{\(\)\s*=>\s*setPreference\(value\)\}/);
});

test("the application remains wired to the same-origin AG-UI runtime provider", async () => {
  const [provider, client, layout, route] = await Promise.all([
    readSource("app/MyRuntimeProvider.tsx"),
    readSource("lib/product-chat/client.ts"),
    readSources(["app/app/layout.tsx", "app/layout.tsx"]),
    readSource("app/api/agui/route.ts"),
  ]);

  assert.match(provider, /from\s+["']@ag-ui\/client["']/);
  assert.match(provider, /\bHttpAgent\b/);
  assert.match(provider, /\buseAgUiRuntime\b/);
  assert.match(provider, /\bAssistantRuntimeProvider\b/);
  assert.match(provider, /\bPRODUCT_AG_UI_BFF_URL\b/);
  assert.match(client, /PRODUCT_AG_UI_BFF_URL\s*=\s*["']\/api\/agui["']/);
  assert.match(layout, /<MyRuntimeProvider\b/);
  assert.match(route, /export\s+async\s+function\s+POST\b/);
  assert.match(route, /text\/event-stream/);
  assert.match(route, /\brelayV3BackendResponse\b/);
  assert.match(route, /["']\/v1\/chat\/ag-ui["']/);
  assert.doesNotMatch(route, /\bRUN_STARTED\b|\bRUN_FINISHED\b/);
});

test("chat and task navigation are composed from assistant-ui primitives", async () => {
  const [thread, threadList, shell] = await Promise.all([
    readSources([
      "components/assistant-ui/thread/layouts/thread-screen.tsx",
      "components/assistant-ui/thread/parts/thread-layout.tsx",
      "components/assistant-ui/thread/parts/thread-message.tsx",
      "components/assistant-ui/thread/parts/thread-message-primitives.tsx",
    ]),
    readSources([
      "components/assistant-ui/thread-list/thread-list-core.tsx",
      "components/assistant-ui/thread-list/thread-list-item.tsx",
    ]),
    readSource(
      "components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx",
    ),
  ]);

  assert.match(thread, /from\s+["']@assistant-ui\/react["']/);
  for (const primitive of [
    "ThreadPrimitive",
    "ComposerPrimitive",
    "MessagePrimitive",
    "ActionBarPrimitive",
    "BranchPickerPrimitive",
  ]) {
    assert.ok(thread.includes(primitive), `missing ${primitive}`);
  }
  assert.doesNotMatch(thread, /<textarea\b/i);

  assert.match(threadList, /\bThreadListRoot\b/);
  assert.match(threadList, /\bThreadListNew\b/);
  assert.match(threadList, /\bThreadListItemPrimitive\b/);
  assert.match(shell, /<Thread[\s\S]{0,180}\bonOpenContextPanel=/);
  assert.match(shell, /<WorkspaceSidebar\b/);
});

test("the official assistant-ui composer is unconditionally docked at the bottom", async () => {
  const thread = await readSources([
    "components/assistant-ui/thread/layouts/thread-screen.tsx",
    "components/assistant-ui/thread/parts/thread-layout.tsx",
    "components/ui/class-names.ts",
  ]);

  assert.match(thread, /<ComposerPrimitive\.Root\b/);
  assert.match(thread, /<ThreadPrimitive\.ViewportFooter\b/);
  assert.match(thread, /data-composer-placement=["']bottom["']/);
  assert.match(
    thread,
    /aui-thread-viewport-footer[^"']*\bsticky\b[^"']*\bbottom-0\b[^"']*\bmt-auto\b/,
  );
  assert.match(thread, /data-slot=["']aui_empty-state["']/);
  assert.match(
    thread,
    /threadEmptyState:\s*["'][^"']*\bflex-1\b[^"']*\bitems-center\b[^"']*\bjustify-center\b/,
  );
  assert.doesNotMatch(thread, /!isEmpty[\s\S]{0,120}\bsticky\b/);
});

test("desktop product sections use reusable canvases while chat stays mounted", async () => {
  const [desktop, view, layout, sidebar, canvas, frame, auxiliary] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/kolibri-workspace/canvas-frame.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx"),
  ]);

  assert.match(desktop, /auxiliary\.openProjects\(\)/);
  assert.match(desktop, /auxiliary\.openReferences\(\)/);
  assert.match(desktop, /openPrimaryFiles/);
  for (const view of ["projects", "documents", "references"]) {
    assert.ok(
      sidebar.includes(
        view === "projects"
          ? "onOpenProjects"
          : view === "documents"
            ? "onOpenDocuments"
            : "onOpenReferenceCatalog",
      ),
      `missing navigation callback: ${view}`,
    );
  }
  assert.doesNotMatch(`${desktop}\n${view}\n${layout}`, /<WorkspaceContextSidebar\b|desktopContextOpen/);
  assert.match(layout, /aria-label=["']Диалог с Kolibri["']/);
  assert.match(layout, /id=["']auxiliary-canvas["']/);
  assert.match(view, /<Thread\b[\s\S]{0,260}workspaceOpen=\{rightWorkspaceOpen\}/);
  assert.match(desktop, /primaryContent=\{auxiliary\.primaryOpen \? auxiliaryCanvas : null\}/);
  assert.match(desktop, /primaryOpen=\{auxiliary\.primaryOpen\}/);
  assert.match(auxiliary, /data-slot=["']auxiliary-canvas["']/);
  assert.match(canvas, /<CanvasFrame\b/);
  assert.match(frame, /data-slot=["']canvas-frame["']/);
  assert.doesNotMatch(`${desktop}\n${view}\n${layout}`, /AssistantChatWidget|CanvasAssistantPane/);
});

test("workspace resizing uses the official assistant-ui registry primitive", async () => {
  const [layout, resizable] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/ui/resizable.tsx"),
  ]);

  assert.match(layout, /from\s+["']@\/components\/ui\/resizable["']/);
  for (const primitive of [
    "ResizablePanelGroup",
    "ResizablePanel",
    "ResizableHandle",
  ]) {
    assert.ok(layout.includes(primitive), `missing ${primitive}`);
  }
  assert.match(resizable, /from\s+["']react-resizable-panels["']/);
  assert.doesNotMatch(layout, /\bPanelResizer\b|\busePanelLayout\b/);
  assert.match(layout, /id=["']project-navigation["']/);
  assert.match(layout, /id=["']primary-workspace["']/);
  assert.match(layout, /id=["']auxiliary-canvas["']/);
});

test("every Canvas tool shares one state-preserving fullscreen control", async () => {
  const [desktop, view, layout, auxiliary, canvas, frame, contextPanel] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/kolibri-workspace/canvas-frame.tsx"),
    readSource("components/kolibri-workspace/context-panel.tsx"),
  ]);

  assert.match(frame, /data-slot=["']canvas-fullscreen-toggle["']/);
  assert.match(frame, /label=\{maximized\s*\?\s*["']Вернуть в панель["']\s*:\s*["']На весь экран["']\}/);
  assert.match(frame, /aria-pressed=\{maximized\}/);
  assert.match(frame, /data-canvas-fullscreen=\{maximized\}/);
  assert.ok(
    frame.indexOf('data-slot="canvas-fullscreen-toggle"') <
      frame.indexOf('role="tabpanel"'),
    "fullscreen control must wrap every file, tool, and Canvas view",
  );
  assert.match(canvas, /<CanvasFrame\b/);

  assert.match(layout, /auxiliaryFullscreen \? auxiliary : null/);
  assert.match(view, /auxiliaryFullscreen=\{auxiliary\.fullscreen\}/);
  assert.match(frame, /data-slot=["']canvas-fullscreen-toggle["']/);
  assert.match(canvas, /<CanvasFrame\b/);
  assert.match(canvas, /onToggleMaximize=\{onToggleMaximize\}/);
  assert.match(auxiliary, /onToggleMaximize=\{controller\.toggleFullscreen\}/);

  for (const mode of ["review", "terminal", "browser", "files"]) {
    assert.ok(contextPanel.includes(`id: "${mode}"`), `missing tool: ${mode}`);
  }
});

test("small browser zoom changes do not flip the workspace into modal mode", async () => {
  const layout = await readSource(
    "components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx",
  );

  assert.match(layout, /data-workspace-mode=["']desktop["']/);
  assert.doesNotMatch(layout, /min-width:\s*1200px/);
  assert.match(layout, /ResizablePanelGroup/);
  assert.match(layout, /minSize=\{640\}/);
});

test("profile and settings have one stable entry in the sidebar footer", async () => {
  const [desktop, view, sidebarProfileFooter, header, canvas] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/sidebar/workspace-sidebar-profile-footer.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
  ]);

  assert.match(sidebarProfileFooter, /data-slot=["']workspace-profile-footer["']/);
  assert.match(
    sidebarProfileFooter,
    /workspace-profile-footer/,
  );
  assert.match(
    sidebarProfileFooter,
    /aria-label=["']Открыть меню личного кабинета["']/,
  );
  assert.match(sidebarProfileFooter, /Суперадминистратор/);

  assert.doesNotMatch(header, /\bonOpenProfileSettings\b/);
  assert.doesNotMatch(
    header,
    /aria-label=["']Открыть меню личного кабинета["']/,
  );
  assert.doesNotMatch(canvas, /\bonOpenProfileSettings\b/);
  assert.doesNotMatch(canvas, /label=["']Открыть личный кабинет["']/);
  assert.match(desktop, /onOpenSettings=\{openSettings\}/);
  assert.match(view, /onOpenProfileSettings=\{\(\) => onOpenSettings\("general"\)\}/);
  assert.doesNotMatch(`${desktop}\n${view}\n${canvas}`, /onOpenProfileSettings=\{\s*openSettings/);
});

test("polished navigation exposes actionable controls and stable account state", async () => {
  const [desktop, view, sidebar, header, profile, thread] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("components/assistant-ui/thread/parts/thread-message.tsx"),
  ]);

  assert.match(header, /data-command-palette-launcher=["']header["']/);
  assert.match(header, /data-context-launcher=["']header["']/);
  assert.doesNotMatch(sidebar, /Запланировано|Плагины/);
  assert.match(desktop, /const openSettings = useCallback/);
  assert.match(desktop, /auxiliary\.openSettings\(section\)/);
  assert.match(view, /onOpenProfileSettings=\{\(\) => onOpenSettings\("general"\)\}/);
  assert.match(profile, /data-slot=["']settings-canvas-content["']/);
  assert.match(thread, /\bhiddenWeatherToolCallIds\b/);
  assert.match(thread, /if\s*\(message\.role\s*===\s*["']user["']\)\s*break/);
});

test("polished workspace recovers placement, saves through reconnects, and reports catalog failures", async () => {
  const [
    desktop,
    view,
    layout,
    auxiliary,
    session,
    estimates,
    projects,
    files,
    fileStates,
    profile,
  ] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas.tsx"),
    readSource("components/kolibri-workspace/canvas-session.ts"),
    readSource("components/assistant-ui/product-widgets/estimate-editor.tsx"),
    readSource("components/kolibri-workspace/projects-overview.tsx"),
    readSource("components/kolibri-workspace/workspace-file-manager.tsx"),
    readSource("components/kolibri-workspace/workspace-file-manager-states.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
  ]);

  assert.match(session, /\bmaximized:\s*boolean\b/);
  assert.match(session, /function\s+updateCanvasTab/);
  assert.match(session, /maximized:\s*input\.maximized \?\? false/);
  assert.match(view, /auxiliaryFullscreen=\{auxiliary\.fullscreen\}/);
  assert.match(layout, /auxiliaryFullscreen \? auxiliary : null/);

  assert.match(estimates, /\bsaveErrorRetryable\b/);
  assert.match(estimates, /\bsaveRetryAttempt\b/);
  assert.match(estimates, /Повторить сохранение/);
  assert.match(estimates, /Math\.min\([\s\S]{0,120}10_000/);

  assert.match(desktop, /catalogState/);
  assert.match(auxiliary, /onRetryWorkspaceCatalog/);
  assert.match(projects, /Не удалось загрузить проекты/);
  assert.match(`${files}\n${fileStates}`, /Не удалось (?:обновить|загрузить) файлы/);
  assert.match(projects, /aria-label=\{`Открыть проект/);
  assert.match(`${files}\n${fileStates}`, /aria-label=\{`Открыть файл/);
  assert.doesNotMatch(projects, /role=["']row["']/);
  assert.doesNotMatch(files, /role=["']row["']/);

  assert.match(profile, /role=["']tablist["']/);
  assert.match(profile, /aria-selected=\{mode\s*===\s*["']login["']\}/);
  assert.match(profile, /role=["']tabpanel["']/);
});

test("the interface does not use blur effects", async () => {
  const sourceFiles = (
    await Promise.all([
      collectSourceFiles("app"),
      collectSourceFiles("components"),
    ])
  ).flat();

  for (const relativePath of sourceFiles) {
    const source = await readSource(relativePath);
    assert.doesNotMatch(
      source,
      /\bblur(?:-|\s*\()/,
      `${relativePath} must not blur the interface`,
    );
  }
});

test("the context panel exposes the four utility tabs accessibly", async () => {
  const panel = await readSource(
    "components/kolibri-workspace/context-panel.tsx",
  );

  assert.match(panel, /\bCONTEXT_PANEL_TABS\b/);

  for (const identifier of ["review", "terminal", "browser", "files"]) {
    assert.ok(
      panel.includes(identifier),
      `missing context tab identifier: ${identifier}`,
    );
  }

  for (const label of ["Проверка", "Терминал", "Браузер", "Файлы"]) {
    assert.ok(panel.includes(label), `missing context tab label: ${label}`);
  }

  assert.match(panel, /role=["']region["']/);
  assert.match(panel, /aria-label=\{activeDefinition\.label\}/);
  assert.match(panel, /aria-labelledby=/);
  assert.doesNotMatch(panel, /role=["']tablist["']/);
  assert.doesNotMatch(panel, /aria-selected=/);
});

test("new shell and workspace sources do not execute arbitrary content", async () => {
  const sourceFiles = (
    await Promise.all([
      collectSourceFiles("components/kolibri-shell"),
      collectSourceFiles("components/kolibri-workspace"),
    ])
  ).flat();

  assert.ok(sourceFiles.length > 0, "expected shell/workspace source files");

  for (const relativePath of sourceFiles) {
    const source = await readSource(relativePath);

    assert.doesNotMatch(
      source,
      /\bdangerouslySetInnerHTML\b/,
      `${relativePath} must not inject raw HTML`,
    );
    assert.doesNotMatch(
      source,
      /\beval\s*\(/,
      `${relativePath} must not evaluate strings`,
    );
    assert.doesNotMatch(
      source,
      /\bnew\s+Function\s*\(/,
      `${relativePath} must not compile arbitrary code`,
    );
  }
});

test("superadmin model connections keep provider secrets transient and bounded", async () => {
  const [
    profile,
    client,
    projection,
    statusRoute,
    enrollmentRoute,
    mimoCredentialRoute,
    codexLoginRoute,
  ] =
    await Promise.all([
      readSource(
        "components/kolibri-shell/profile-settings-surface.tsx",
      ),
      readSource("lib/providers/client.ts"),
      readSource("lib/provider-connections.ts"),
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
    ]);

  for (const label of [
    "Настройки",
    "Суперадминистратор",
    "ИИ и модели",
    "MiMo Code",
    "Codex CLI",
    "Подключения провайдеров",
  ]) {
    assert.ok(profile.includes(label), `missing superadmin label: ${label}`);
  }

  assert.match(
    client,
    /request\(\s*["']\/api\/superadmin\/provider-connections["']/,
  );
  const aiModelsSection = profile.slice(
    profile.indexOf("function AiModelsSection"),
    profile.indexOf("function SecuritySection"),
  );
  assert.match(aiModelsSection, /user\.isPlatformOwner/);
  assert.match(aiModelsSection, /type\s*=\s*["']password["']/i);
  assert.match(aiModelsSection, /autoComplete=["']off["']/);
  assert.match(aiModelsSection, /\bconnectMimo\b/);
  assert.match(aiModelsSection, /\bconnectCodexLogin\b/);
  assert.match(
    aiModelsSection,
    /<AgentProfileSelector\s+surface=["']settings["']\s*\/>/,
  );
  assert.doesNotMatch(aiModelsSection, /AGENT_PROFILES\.map/);
  assert.match(aiModelsSection, /setMimoKey\(["']["']\)/);
  assert.doesNotMatch(
    `${profile}\n${client}`,
    /\blocalStorage\b|\bsessionStorage\b/,
  );
  assert.match(profile, /data-slot=["']settings-canvas-mobile-navigation["']/);
  assert.match(profile, /aria-label=["']Все настройки["']/);
  assert.match(
    client,
    /["']\/api\/superadmin\/provider-connections\/mimo-code\/credential["']/,
  );
  assert.match(
    client,
    /["']\/api\/superadmin\/provider-connections\/codex-cli\/login-status["']/,
  );
  assert.doesNotMatch(client, /\/api\/v3\/providers/);

  for (const providerId of ["mimo-code", "codex-cli"]) {
    assert.ok(projection.includes(providerId), `missing provider ${providerId}`);
  }
  assert.match(projection, /\bfunction\s+isProviderId\b/);
  assert.doesNotMatch(projection, /\brawToken\b|\brawPassword\b/);

  assert.match(statusRoute, /export\s+async\s+function\s+GET\b/);
  assert.match(enrollmentRoute, /export\s+async\s+function\s+POST\b/);
  assert.match(mimoCredentialRoute, /maxRequestBytes:\s*12\s*\*\s*1_024/);
  assert.match(codexLoginRoute, /maxRequestBytes:\s*0/);
  assert.match(enrollmentRoute, /\bisProviderId\b/);
  assert.match(enrollmentRoute, /\bproxyV3JsonRequest\b/);
  const providerServerSources = `${projection}\n${statusRoute}\n${enrollmentRoute}`;
  assert.doesNotMatch(
    providerServerSources,
    /KOLIBRI_PROVIDER_AUTHORITY_ADMIN_(?:URL|TOKEN)/,
  );
  assert.match(statusRoute, /["']\/v1\/provider-connections["']/);
  assert.match(
    enrollmentRoute,
    /`\/v1\/provider-connections\/\$\{providerId\}\/enrollment-intents`/,
  );
  assert.doesNotMatch(
    enrollmentRoute,
    /searchParams\.get\(\s*["'](?:url|upstream|baseUrl)["']/,
  );
});

test("provider enrollment is gated by the canonical revocable V3 session", async () => {
  const [projection, backend, security, statusRoute, enrollmentRoute] =
    await Promise.all([
      readSource("lib/provider-connections.ts"),
      readSource("backend/app/provider_connections.py"),
      readSource("backend/app/security.py"),
      readSource("app/api/superadmin/provider-connections/route.ts"),
      readSource(
        "app/api/superadmin/provider-connections/[providerId]/enrollments/route.ts",
      ),
    ]);

  assert.match(projection, /\bfunction\s+isProviderId\b/);
  assert.match(backend, /\bDepends\(require_owner\)/);
  assert.match(backend, /\bDepends\(require_mutation_auth\)/);
  assert.match(
    security,
    /def require_mutation_auth[\s\S]*?require_bearer_session[\s\S]*?require_same_origin[\s\S]*?require_csrf/,
  );
  assert.match(backend, /provider_enrollment_reauthentication_required/);
  assert.match(backend, /owner_authorization_decision_id/);
  assert.match(enrollmentRoute, /\bproxyV3JsonRequest\b/);
  assert.match(statusRoute, /\bproxyV3JsonRequest\b/);
  assert.doesNotMatch(
    `${statusRoute}\n${enrollmentRoute}`,
    /KOLIBRI_PROVIDER_AUTHORITY|\bAuthorization\b/,
  );
});

test("workspace tools stay closed until their dedicated controls are used", async () => {
  const hook = await readSource(
    "components/kolibri-shell/desktop-workspace/use-auxiliary-canvas.ts",
  );

  assert.match(hook, /const \[visible, setVisible\] = useState\(false\)/);
  assert.match(hook, /const open = visible && activeTab !== null/);
  assert.match(hook, /const toggle = useCallback/);
  assert.match(hook, /setVisible\(true\)/);
  assert.match(hook, /openTool/);
});

test("documents reuse one primary Canvas surface and minimized work is restorable", async () => {
  const [desktop, view, session, shelf] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-workspace/canvas-session.ts"),
    readSource(
      "components/kolibri-workspace/workspace-task-shelf.tsx",
    ),
  ]);

  assert.match(desktop, /openPrimaryFiles/);
  assert.match(view, /onOpenDocuments=\{onOpenDocuments\}/);
  assert.match(view, /<WorkspaceTaskShelf\b/);
  assert.match(desktop, /auxiliaryCanvas=\{auxiliaryCanvas\}/);
  assert.doesNotMatch(desktop, /<WorkspaceFileManager\b|<WorkspaceArtifactEditor\b/);
  assert.match(session, /\bcreateCanvasSession\b/);
  assert.match(session, /\bopenCanvasTab\b/);
  assert.match(session, /\bminimizeCanvasTab\b/);
  assert.match(session, /\brestoreCanvasTab\b/);
  assert.doesNotMatch(session, /kind:\s*["']desktop["']/);
  assert.match(session, /kind:\s*["']files["']/);
  assert.match(shelf, /aria-label=\{`Восстановить вкладку/);
});

test("desktop navigation removes the old route and exposes an auxiliary canvas", async () => {
  const [desktop, layout, sidebarConstants, sidebarNavigation, header, canvas, thread] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace.tsx"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx"),
    readSource("components/kolibri-shell/sidebar/constants.ts"),
    readSource("components/kolibri-shell/sidebar/workspace-sidebar-navigation.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/assistant-ui/thread/parts/thread-layout.tsx"),
  ]);

  assert.doesNotMatch(`${desktop}\n${layout}`, /kind:\s*["']desktop["']|Рабочий стол/);
  assert.match(layout, /data-workspace-mode=["']desktop["']/);
  assert.doesNotMatch(sidebarConstants, /label:\s*["']Рабочий стол["']/);
  assert.doesNotMatch(sidebarNavigation, /onOpenDesktop/);
  assert.match(header, /contextPanelOpen\s*\?\s*["']Скрыть контекст["']\s*:\s*["']Показать контекст["']/);
  assert.match(header, /aria-controls=["']workspace-canvas["']/);
  assert.doesNotMatch(`${desktop}\n${layout}`, /<WorkspaceContextSidebar\b|desktopContextOpen/);
  assert.match(layout, /id=["']auxiliary-canvas["']/);
  assert.doesNotMatch(canvas, /data-slot=["']canvas-open-desktop["']/);
  assert.match(thread, /aui-composer-open-context/);
  assert.match(thread, /<ComposerPrimitive\.Root\b/);
});

test("immersive Canvas keeps minimized work recoverable and manages focus", async () => {
  const [hook, view, header, canvas, thread] = await Promise.all([
    readSource("components/kolibri-shell/desktop-workspace/use-auxiliary-canvas.ts"),
    readSource("components/kolibri-shell/desktop-workspace/desktop-workspace-view.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/assistant-ui/thread/parts/thread-layout.tsx"),
  ]);

  assert.match(hook, /open && activeTab\?\.placement === ["']right["'] && Boolean\(activeTab\.maximized\)/);
  assert.match(hook, /toggleFullscreen/);
  assert.match(hook, /minimizeCanvasTab/);
  assert.match(view, /<WorkspaceTaskShelf\b/);
  assert.match(header, /data-context-launcher=["']header["']/);
  assert.doesNotMatch(canvas, /data-canvas-launcher=["']canvas["']/);
  assert.match(thread, /data-context-launcher=["']composer["']/);
});
