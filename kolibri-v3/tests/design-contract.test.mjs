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
  const thread = await readSource("components/assistant-ui/thread.tsx");

  assert.match(thread, /\bKolibri\b/i);

  const suggestions =
    thread.match(/<ThreadPrimitive\.Suggestion\b/g) ?? [];
  const prompts = thread.match(/\bprompt\s*=/g) ?? [];

  assert.equal(suggestions.length, 7);
  assert.equal(prompts.length, 7);

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
  const [shell, header, sidebar, thread, threadList, theme, layout, css] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/mobile-workspace-header.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/assistant-ui/thread.tsx"),
    readSource("components/assistant-ui/thread-list.tsx"),
    readSource("components/theme/kolibri-theme-provider.tsx"),
    readSource("app/layout.tsx"),
    readSource("app/globals.css"),
  ]);

  assert.match(shell, /isDesktop\s*\?\s*\([\s\S]*<WorkspaceHeader\b/);
  assert.match(shell, /<MobileWorkspaceHeader\b/);
  assert.match(shell, /<Thread[\s\S]{0,100}\bcompact=\{!isDesktop\}/);
  assert.match(header, /<ThreadListPrimitive\.New\b/);
  assert.match(header, /Открыть меню/);
  assert.match(header, /aria-expanded=\{navigationOpen\}/);
  assert.match(shell, /navigationOpen=\{mobileNavigationOpen\}/);
  assert.match(header, /data-slot=["']mobile-hamburger-icon["']/);
  assert.match(header, /data-slot=["']mobile-editor-back["']/);
  assert.match(header, /aria-label=["']На основной экран["']/);
  assert.match(sidebar, /previewDisabled=\{isOverlay\}/);
  assert.match(
    sidebar,
    /if\s*\(previewDisabled\)\s*return\s+destinationButton/,
  );
  assert.match(shell, /data-slot=["']mobile-account-sheet["']/);
  assert.match(shell, /top-\[env\(safe-area-inset-top\)\]/);
  assert.match(shell, /rounded-r-\[2\.5rem\]/);
  assert.match(shell, /slide-in-from-left-full/);
  assert.match(shell, /canvasOpen\s*&&\s*canvasFile/);
  assert.match(
    shell,
    /onBack=\{[\s\S]{0,100}canvasOpen\s*\?\s*\(\)\s*=>\s*openPrimaryDestination\(["']chat["']\)/,
  );
  assert.match(shell, /openPrimaryDestination\(["']chat["']\)/);
  assert.match(
    shell,
    /isDesktop\s*&&\s*canvasMaximized\s*&&\s*placement\s*===\s*["']primary["']/,
  );
  assert.match(
    shell,
    /if\s*\(!isDesktop\)\s*\{[\s\S]{0,120}setCanvasMaximized\(false\)/,
  );
  assert.match(
    shell,
    /maximized:\s*isDesktop\s*&&[\s\S]{0,180}\bstoredPrimaryTab\b/,
  );
  assert.doesNotMatch(
    shell,
    /const toggleNavigation[\s\S]{0,420}else\s*\{[\s\S]{0,100}setCanvasVisible/,
  );
  assert.doesNotMatch(
    shell,
    /const openAccountSettings[\s\S]{0,520}setCanvasVisible/,
  );
  assert.match(
    shell,
    /const mobilePrimaryCanvasMounted\s*=\s*activeCanvasTab\s*!==\s*null\s*&&\s*canvasPlacement\s*===\s*["']primary["']/,
  );
  assert.match(
    shell,
    /data-slot=["']mobile-primary-workspace["'][\s\S]{0,220}inert=\{mobilePrimaryWorkspaceHidden/,
  );
  assert.equal(
    (header.match(/h-\[2\.5px\]\s+w-full\s+rounded-full\s+bg-current/g) ?? [])
      .length,
    2,
  );
  assert.match(header, /aria-label=["']Chat\. Выбрать раздел["']/);
  assert.match(header, /Рабочий стол/);
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
  assert.match(sidebar, /shouldCloseThreadDrawerForClick/);
  assert.match(css, /\[data-slot=["']workspace-file-category-tabs["']\]/);
  assert.doesNotMatch(css, /\.border-border\\\/80\.flex\.gap-1/);
  assert.match(theme, /KOLIBRI_THEME_STORAGE_KEY\s*=\s*["']kolibri-theme["']/);
  assert.match(theme, /prefers-color-scheme:\s*dark/);
  assert.match(layout, /<KolibriThemeProvider\b/);
  assert.match(layout, /\bthemeBootScript\b/);
  assert.match(css, /@media\s*\(max-width:\s*959px\)/);
  assert.match(css, /--background:\s*#000000/);
  assert.match(css, /--background:\s*#ffffff/);
  assert.match(css, /-webkit-touch-callout:\s*none/);
  assert.match(css, /touch-action:\s*pan-y/);
  assert.doesNotMatch(thread, /aui-composer-voice-submit-icon/);
  assert.match(thread, /composerEmpty\s*\|\|/);
  assert.match(thread, /Голосовой ввод недоступен/);
});

test("mobile runtime uses iOS and Android viewport primitives", async () => {
  const [environment, layout, css] = await Promise.all([
    readSource("components/kolibri-shell/mobile-environment.tsx"),
    readSource("app/layout.tsx"),
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
  const editor = await readSource(
    "components/assistant-ui/product-widgets.tsx",
  );

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
    "components/assistant-ui/product-widgets.tsx",
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
    readSource("app/layout.tsx"),
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
    readSource("components/assistant-ui/thread.tsx"),
    readSource("components/assistant-ui/thread-list.tsx"),
    readSource("components/kolibri-shell/workspace-shell.tsx"),
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

  assert.match(threadList, /\bThreadListPrimitive\b/);
  assert.match(threadList, /\bThreadListItemPrimitive\b/);
  assert.match(shell, /<Thread[\s\S]{0,180}\bonOpenDesktop=/);
  assert.match(shell, /<WorkspaceSidebar\b/);
});

test("the official assistant-ui composer is unconditionally docked at the bottom", async () => {
  const thread = await readSource("components/assistant-ui/thread.tsx");

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
    /aui_empty-state[\s\S]{0,180}\bflex-1\b[\s\S]{0,100}\bitems-center\b[\s\S]{0,100}\bjustify-center\b/,
  );
  assert.doesNotMatch(thread, /!isEmpty[\s\S]{0,120}\bsticky\b/);
});

test("primary product sections replace chat while assistant-ui stays available as a pinnable widget", async () => {
  const [shell, sidebar, widget] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/assistant-ui/assistant-chat-widget.tsx"),
  ]);

  for (const view of ["projects", "documents", "references"]) {
    assert.ok(shell.includes(`"${view}"`), `missing primary view: ${view}`);
  }

  for (const callback of [
    "onOpenProjects",
    "onOpenDocuments",
    "onOpenReferenceCatalog",
  ]) {
    assert.ok(sidebar.includes(callback), `missing navigation callback: ${callback}`);
  }

  assert.match(widget, /\bAssistantModalPrimitive\b/);
  assert.match(widget, /<AssistantModalPrimitive\.Root\b/);
  assert.match(widget, /<AssistantModalPrimitive\.Trigger\b/);
  assert.match(widget, /<AssistantModalPrimitive\.Content\b/);
  assert.match(widget, /\bPinIcon\b/);
  assert.match(widget, /\bPinOffIcon\b/);
  assert.match(widget, /<Thread\b[^>]*\/>/);
  assert.match(widget, /\bonOpenDesktop\b/);
});

test("workspace resizing uses the official assistant-ui registry primitive", async () => {
  const [shell, resizable] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/ui/resizable.tsx"),
  ]);

  assert.match(
    shell,
    /from\s+["']@\/components\/ui\/resizable["']/,
  );
  for (const primitive of [
    "ResizablePanelGroup",
    "ResizablePanel",
    "ResizableHandle",
  ]) {
    assert.ok(shell.includes(primitive), `missing ${primitive}`);
  }
  assert.match(resizable, /from\s+["']react-resizable-panels["']/);
  assert.doesNotMatch(shell, /\bPanelResizer\b/);
  assert.doesNotMatch(shell, /\busePanelLayout\b/);
  assert.match(shell, /from\s+["']@\/components\/ui\/dialog["']/);
});

test("every Canvas tool shares one state-preserving fullscreen control", async () => {
  const [shell, canvas, contextPanel] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/kolibri-workspace/context-panel.tsx"),
  ]);

  assert.match(canvas, /data-slot=["']canvas-fullscreen-toggle["']/);
  assert.match(canvas, /label=\{maximized\s*\?\s*["']Вернуть в панель["']\s*:\s*["']На весь экран["']\}/);
  assert.match(canvas, /aria-pressed=\{maximized\}/);
  assert.match(canvas, /data-canvas-fullscreen=\{maximized\}/);
  assert.ok(
    canvas.indexOf('data-slot="canvas-fullscreen-toggle"') <
      canvas.indexOf('id="canvas-active-tabpanel"'),
    "fullscreen control must wrap every file, tool, and Canvas view",
  );

  const singletonSurfaces =
    shell.match(/data-canvas-surface=["']singleton["']/g) ?? [];
  const canvasWorkspaceInstances =
    shell.match(/<CanvasWorkspace\b/g) ?? [];
  const fullscreenToggles =
    shell.match(/\bonToggleMaximize=\{/g) ?? [];
  const controlledTools = shell.match(/\btoolMode=\{canvasTool\}/g) ?? [];
  const controlledFiles = shell.match(/\bselectedFile=\{canvasFile\}/g) ?? [];

  assert.equal(singletonSurfaces.length, 1);
  assert.equal(canvasWorkspaceInstances.length, 1);
  assert.equal(fullscreenToggles.length, 1);
  assert.equal(controlledTools.length, 1);
  assert.equal(controlledFiles.length, 1);
  assert.match(shell, /fixed inset-0 z-50 h-dvh w-dvw/);
  assert.match(shell, /canvasMaximized\s*\?\s*["']w-dvw border-x-0["']/);
  assert.doesNotMatch(
    shell,
    /\{canvasMaximized\s*\?\s*\(\s*<div[^>]+id=["']workspace-canvas["']/,
  );

  for (const mode of [
    "review",
    "calculations",
    "browser",
    "files",
    "subtask",
  ]) {
    assert.ok(contextPanel.includes(`id: "${mode}"`), `missing tool: ${mode}`);
  }
});

test("small browser zoom changes do not flip the workspace into modal mode", async () => {
  const shell = await readSource(
    "components/kolibri-shell/workspace-shell.tsx",
  );

  assert.match(shell, /\bDESKTOP_ENTER_WIDTH\b/);
  assert.match(shell, /\bDESKTOP_EXIT_WIDTH\b/);
  assert.match(shell, /DESKTOP_ENTER_WIDTH\s*=\s*960/);
  assert.match(shell, /DESKTOP_EXIT_WIDTH\s*=\s*860/);
  assert.match(shell, /window\.addEventListener\(["']resize["']/);
  assert.match(shell, /data-workspace-mode=["']desktop["']/);
  assert.match(shell, /data-workspace-mode=["']compact["']/);
  assert.doesNotMatch(shell, /min-width:\s*1200px/);
});

test("profile and settings have one stable entry in the sidebar footer", async () => {
  const [shell, sidebar, header, canvas] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
  ]);

  assert.match(sidebar, /data-slot=["']workspace-profile-footer["']/);
  assert.match(
    sidebar,
    /workspace-profile-footer[\s\S]{0,220}\bsticky\b[\s\S]{0,100}\bbottom-0\b/,
  );
  assert.match(
    sidebar,
    /aria-label=["']Открыть меню личного кабинета["']/,
  );
  assert.match(sidebar, /Суперадминистратор/);

  assert.doesNotMatch(header, /\bonOpenProfileSettings\b/);
  assert.doesNotMatch(
    header,
    /aria-label=["']Открыть меню личного кабинета["']/,
  );
  assert.doesNotMatch(canvas, /\bonOpenProfileSettings\b/);
  assert.doesNotMatch(canvas, /label=["']Открыть личный кабинет["']/);
  assert.doesNotMatch(
    shell,
    /<WorkspaceHeader[\s\S]{0,650}\bonOpenProfileSettings=/,
  );
  assert.doesNotMatch(
    shell,
    /<CanvasWorkspace[\s\S]{0,700}\bonOpenProfileSettings=/,
  );
});

test("polished navigation exposes actionable controls and stable account state", async () => {
  const [shell, sidebar, header, profile, thread] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("components/assistant-ui/thread.tsx"),
  ]);

  assert.doesNotMatch(header, /\bArrowLeft\b|\bArrowRight\b|\bEllipsis\b/);
  assert.doesNotMatch(sidebar, /Запланировано|Плагины/);
  assert.match(
    shell,
    /onOpenProfileSettings:\s*\(\)\s*=>\s*openAccountSettings\(\)/,
  );
  assert.match(shell, /activeSection=\{accountSection\}/);
  assert.match(profile, /<main[\s\S]{0,260}\bflex-1\b/);
  assert.match(thread, /\bhiddenWeatherToolCallIds\b/);
  assert.match(thread, /if\s*\(message\.role\s*===\s*["']user["']\)\s*break/);
});

test("polished workspace recovers placement, saves through reconnects, and reports catalog failures", async () => {
  const [
    shell,
    session,
    estimates,
    projects,
    files,
    profile,
  ] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-workspace/canvas-session.ts"),
    readSource("components/assistant-ui/product-widgets.tsx"),
    readSource("components/kolibri-workspace/projects-overview.tsx"),
    readSource("components/kolibri-workspace/workspace-file-manager.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
  ]);

  assert.match(session, /\bmaximized:\s*boolean\b/);
  assert.match(
    shell,
    /setCanvasPlacement\(nextTab\.placement\);[\s\S]{0,120}setCanvasMaximized\(nextTab\.maximized\);/,
  );
  assert.doesNotMatch(
    shell,
    /nextTab\?\.content\.kind\s*===\s*["']desktop["']/,
  );
  assert.match(
    shell,
    /onPlacementChange=\{isDesktop\s*\?\s*moveCanvas\s*:\s*undefined\}/,
  );

  assert.match(estimates, /\bsaveErrorRetryable\b/);
  assert.match(estimates, /\bsaveRetryAttempt\b/);
  assert.match(estimates, /Повторить сохранение/);
  assert.match(estimates, /Math\.min\([\s\S]{0,120}10_000/);

  assert.match(shell, /\bworkspaceCatalogState\b/);
  assert.match(projects, /Не удалось загрузить проекты/);
  assert.match(files, /Не удалось загрузить файлы/);
  assert.match(projects, /aria-label=\{`Открыть проект/);
  assert.match(files, /aria-label=\{`Открыть файл/);
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

test("the context panel exposes the five utility tabs accessibly", async () => {
  const panel = await readSource(
    "components/kolibri-workspace/context-panel.tsx",
  );

  assert.match(panel, /\bCONTEXT_PANEL_TABS\b/);

  for (const identifier of [
    "review",
    "calculations",
    "browser",
    "files",
    "subtask",
  ]) {
    assert.ok(
      panel.includes(identifier),
      `missing context tab identifier: ${identifier}`,
    );
  }

  for (const label of [
    "Проверка",
    "Расчёты",
    "Браузер",
    "Файлы",
    "Дополнительная задача",
  ]) {
    assert.ok(panel.includes(label), `missing context tab label: ${label}`);
  }

  for (const role of ["tablist", "tab", "tabpanel"]) {
    assert.match(
      panel,
      new RegExp(`role\\s*=\\s*["']${role}["']`),
      `missing ${role} semantics`,
    );
  }

  for (const attribute of [
    "aria-selected",
    "aria-controls",
    "aria-labelledby",
  ]) {
    assert.match(
      panel,
      new RegExp(`${attribute}\\s*=`),
      `missing ${attribute}`,
    );
  }
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
    "Личный кабинет",
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
  assert.match(profile, /\bmobileMenuOpen\b/);
  assert.match(profile, /setMobileMenuOpen\(false\)/);
  assert.match(profile, /setMobileMenuOpen\(true\)/);
  assert.match(profile, />\s*Все настройки\s*</);
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
  const shell = await readSource(
    "components/kolibri-shell/workspace-shell.tsx",
  );

  assert.match(
    shell,
    /previousDesktopState\.current\s*=\s*isDesktop;[\s\S]*?setNavigationPinned\(isDesktop\);/,
  );
  assert.doesNotMatch(
    shell,
    /previousDesktopState\.current\s*=\s*isDesktop;[\s\S]{0,300}setCanvasVisible\(false\)/,
  );
  assert.match(shell, /const\s+\[canvasVisible,\s*setCanvasVisible\]/);
});

test("documents reuse one primary Canvas surface and minimized work is restorable", async () => {
  const [shell, session, shelf] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-workspace/canvas-session.ts"),
    readSource(
      "components/kolibri-workspace/workspace-task-shelf.tsx",
    ),
  ]);

  assert.match(shell, /const PRIMARY_CANVAS_TAB_ID\s*=\s*["']workspace-primary["']/);
  assert.match(
    shell,
    /view\s*===\s*["']documents["'][\s\S]*?openCurrentFileSection\(\s*["']all["']/,
  );
  assert.match(shell, /:\s*["']workspace:files["']/);
  assert.match(
    shell,
    /openProjectSection[\s\S]*?id:\s*PRIMARY_CANVAS_TAB_ID/,
  );
  assert.doesNotMatch(
    shell,
    /<WorkspaceFileManager\b|<WorkspaceArtifactEditor\b/,
  );
  assert.match(shell, /\bcreateCanvasSession\b/);
  assert.match(shell, /\bopenCanvasTab\b/);
  assert.match(shell, /\bminimizeCanvasTab\b/);
  assert.match(shell, /\brestoreCanvasTab\b/);
  assert.match(shell, /<WorkspaceTaskShelf\b/);
  assert.match(session, /kind:\s*["']desktop["']/);
  assert.match(session, /kind:\s*["']files["']/);
  assert.match(shelf, /aria-label=\{`Восстановить вкладку/);
});

test("the single desktop is discoverable from navigation, header, Canvas, and chat", async () => {
  const [shell, sidebar, header, canvas, thread] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/assistant-ui/thread.tsx"),
  ]);

  assert.match(shell, /const PRIMARY_CANVAS_TAB_ID\s*=\s*["']workspace-primary["']/);
  assert.match(
    shell,
    /storedPrimaryTab\?\.content\.kind\s*===\s*["']desktop["'][\s\S]{0,100}storedPrimaryTab\.maximized[\s\S]{0,50}:\s*true/,
  );
  assert.match(shell, /data-workspace-mode=["']immersive["']/);
  assert.match(sidebar, /label:\s*["']Рабочий стол["']/);
  assert.match(sidebar, /\bonOpenDesktop\b/);
  assert.match(
    header,
    /canvasOpen\s*\?\s*["']Скрыть рабочую область["']\s*:\s*["']Открыть рабочий стол["']/,
  );
  assert.match(canvas, /data-slot=["']canvas-open-desktop["']/);
  assert.match(thread, /aui-composer-open-desktop/);
  assert.match(thread, /<ComposerPrimitive\.Root\b/);
});

test("immersive Canvas keeps minimized work recoverable and manages focus", async () => {
  const [shell, sidebar, header, canvas, thread] = await Promise.all([
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/assistant-ui/thread.tsx"),
  ]);

  assert.match(
    shell,
    /if\s*\(canvasOpen\s*&&\s*canvasMaximized\)[\s\S]{0,900}<WorkspaceTaskShelf\b/,
  );
  assert.match(
    shell,
    /#workspace-canvas \[role="tab"\]\[aria-selected="true"\]/,
  );
  assert.match(shell, /canvasReturnFocusLauncherRef/);
  assert.match(shell, /\[data-canvas-launcher="\$\{launcherId\}"\]/);

  assert.match(sidebar, /data-canvas-launcher=\{launcherId\}/);
  assert.match(header, /data-canvas-launcher=["']header["']/);
  assert.match(canvas, /data-canvas-launcher=["']canvas["']/);
  assert.match(thread, /data-canvas-launcher=["']composer["']/);
});
