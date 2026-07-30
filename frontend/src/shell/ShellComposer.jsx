import { useState } from "react";
import { Composer } from "./Composer";

export function ShellComposer({
  availableTools = [],
  busy,
  executionModes = ["fast"],
  onExecutionMode,
  onProjectPatch,
  onSend,
  project,
}) {
  const [value, setValue] = useState("");
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  if (!project) return null;
  const supportedModes = executionModes.length ? executionModes : ["fast"];
  const executionMode = supportedModes.includes(project.executionMode) ? project.executionMode : "fast";
  const selectedTool = project.draftTool || "";
  const submit = (text) => {
    const clean = text.trim();
    if (!clean || busy) return;
    onSend(project.id, clean, selectedTool, executionMode);
    setValue("");
  };

  return (
    <footer className="shell-composer-footer" data-testid="shell-composer-footer">
      <Composer
        availableTools={availableTools}
        busy={busy}
        embedded
        executionMode={executionMode}
        executionModes={supportedModes}
        onChange={setValue}
        onExecutionMode={(mode) => onExecutionMode?.(project.id, mode)}
        onSubmit={submit}
        onTool={(tool) => onProjectPatch(project.id, { draftTool: tool, viewMode: "dialog" })}
        selectedTool={selectedTool}
        setToolMenuOpen={setToolMenuOpen}
        toolMenuOpen={toolMenuOpen}
        value={value}
      />
    </footer>
  );
}
