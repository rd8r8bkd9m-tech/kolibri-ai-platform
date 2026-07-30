import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

test("composer uses the official model context with compact cascading selectors", async () => {
  const [
    thread,
    selector,
    registry,
    identity,
    settings,
    dropdown,
    runtime,
    client,
  ] =
    await Promise.all([
    readSource("components/assistant-ui/thread.tsx"),
    readSource("components/assistant-ui/agent-profile-selector.tsx"),
    readSource("components/assistant-ui/model-selector.tsx"),
    readSource("lib/identity/provider.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
    readSource("components/ui/dropdown-menu.tsx"),
    readSource("app/MyRuntimeProvider.tsx"),
    readSource("lib/product-chat/client.ts"),
  ]);

  assert.match(thread, /<AgentProfileSelector\s*\/>/);
  assert.match(thread, /<AgentProfileSelector control=["']developer["']\s*\/>/);
  assert.match(settings, /<AgentProfileSelector surface=["']settings["']\s*\/>/);
  assert.match(
    settings,
    /<AgentProfileSelector surface=["']settings["'] control=["']developer["']\s*\/>/,
  );
  assert.doesNotMatch(thread, /DeveloperAccessSelector|DeveloperAgentToggle/);

  assert.match(selector, /from\s+["']@\/components\/assistant-ui\/model-selector["']/);
  assert.match(selector, /<ModelSelector\.Root/);
  assert.match(selector, /\bpreferredAgentProfile\b/);
  assert.match(selector, /identity\.setModelSettings\(\{/);
  assert.match(selector, /\bmodelSettingsSaving\b/);
  assert.match(selector, /aria-busy=\{saving\}/);
  assert.match(selector, /role=["']alert["']/);
  assert.match(selector, /Повторить/);
  assert.doesNotMatch(selector, /\bbackdrop-blur\b/);
  assert.doesNotMatch(registry, /\bbackdrop-blur\b/);
  assert.doesNotMatch(selector, /localStorage|sessionStorage/);
  assert.match(identity, /\bagentProfileSaving\b/);
  assert.match(identity, /\bmodelSettingsSaving\b/);
  assert.match(selector, /developerMode\.available/);
  assert.match(selector, /aria-label=\{triggerAccessibleLabel\}/);
  assert.match(selector, /`Модель: \$\{modelName\}`/);
  assert.match(selector, /useSyncExternalStore\(/);
  assert.match(selector, /type MobilePage = ["']root["'] \| ["']model["'] \| ["']effort["'] \| ["']speed["']/);
  assert.match(selector, /mobilePage !== ["']root["']/);
  assert.match(selector, /event\.key === ["']ArrowLeft["']/);
  assert.match(selector, /backRef\.current\?\.focus\(\)/);
  assert.match(selector, /DropdownMenuSubTrigger/);
  assert.match(selector, /DropdownMenuSubContent/);
  assert.match(selector, /DropdownMenuRadioItem/);
  assert.match(selector, /keepMenuOpen\(event\)/);
  assert.doesNotMatch(selector, /\b(BotIcon|Code2Icon|SparklesIcon)\b/);
  assert.doesNotMatch(selector, /\bicon:\s*model/);
  assert.match(selector, /Модель/);
  assert.match(selector, /Усилие/);
  assert.match(selector, /Скорость/);
  assert.match(selector, /max:\s*["']Макс\.["']/);
  assert.match(selector, /ultra:\s*["']Ультра["']/);
  assert.match(selector, /serviceTier:\s*nextServiceTier/);
  assert.match(selector, /preferredServiceTier/);
  assert.match(selector, /Скорость 1,5×/);
  assert.match(selector, /Полный доступ/);
  assert.match(selector, /Dev-режим: полный доступ/);
  assert.match(selector, /developerMode\.setMode\(mode\)/);
  assert.match(selector, /mobilePageRef\.current !== ["']model["']/);
  assert.doesNotMatch(
    client,
    /executionMode === ["']developer["']\s*\?\s*["']codex-cli["']/,
  );
  assert.match(client, /agentProfile:\s*profile/);
  assert.match(runtime, /getAccessMode/);
  assert.match(runtime, /developerAccessMode !== ["']standard["']/);
  assert.match(selector, /min-w-0/);
  assert.match(selector, /calc\(100vw-1rem\)/);

  assert.match(registry, /role=["']combobox["']/);
  assert.match(registry, /aria-haspopup=["']listbox["']/);
  assert.match(registry, /ModelSelectorFocusAnchor/);
  assert.match(registry, /closeOnSelect\?:\s*boolean/);
  assert.match(registry, /if\s*\(closeOnSelect\)\s*setOpen\(false\)/);
  assert.match(registry, /ModelSelectorModelContext/);
  assert.match(dropdown, /DropdownMenuPrimitive\.SubContent/);
  assert.match(dropdown, /DropdownMenuPrimitive\.ItemIndicator/);
  assert.match(dropdown, /CheckIcon/);
});
