import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const toolGroup = readFileSync(
  new URL("../components/assistant-ui/tool-group.tsx", import.meta.url),
  "utf8",
);
const developerActivity = readFileSync(
  new URL(
    "../components/assistant-ui/developer-activity-tool.tsx",
    import.meta.url,
  ),
  "utf8",
);

test("tool activity stays collapsed and uses a bounded internal scroller", () => {
  assert.match(toolGroup, /defaultOpen = false/);
  assert.match(toolGroup, /data-slot="tool-group-scroll-region"/);
  assert.match(toolGroup, /max-h-\[42dvh\]/);
  assert.match(toolGroup, /overflow-y-auto/);
  assert.match(toolGroup, /overscroll-contain/);
  assert.doesNotMatch(toolGroup, /\[&>\*\]:animate-in/);
});

test("developer command and file rows are independently collapsed", () => {
  assert.match(
    developerActivity,
    /<details[\s\S]*aria-label="Команда агента-разработчика"/,
  );
  assert.match(
    developerActivity,
    /<details[\s\S]*aria-label="Изменения файлов агентом-разработчиком"/,
  );
  assert.match(
    developerActivity,
    /group-open\/developer-tool:rotate-90/g,
  );
});
