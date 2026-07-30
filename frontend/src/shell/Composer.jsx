import { useEffect, useRef, useState } from "react";
import { ArrowUp, ChevronDown, Code2, Gauge, Plus, X } from "lucide-react";
import { EXECUTION_MODES } from "../app/constants";
import { ComposerModeMenu } from "./ComposerModeMenu";
import { ComposerToolMenu } from "./ComposerToolMenu";

export function Composer({
  availableTools = [],
  busy,
  embedded = false,
  executionMode = "fast",
  executionModes = ["fast"],
  selectedTool,
  value,
  onChange,
  onSubmit,
  onExecutionMode,
  onTool,
  toolMenuOpen,
  setToolMenuOpen,
}) {
  const input = useRef(null);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const selected = availableTools.find((item) => item.id === selectedTool);
  const SelectedIcon = selected?.icon;
  const supportedModes = EXECUTION_MODES.filter((mode) => executionModes.includes(mode.id));
  const currentMode = supportedModes.find((mode) => mode.id === executionMode) || supportedModes[0] || EXECUTION_MODES[0];
  const CurrentModeIcon = currentMode.id === "codex" ? Code2 : Gauge;
  const submit = () => {
    if (value.trim() && !busy) onSubmit(value);
  };

  useEffect(() => {
    const coarsePointer = globalThis.matchMedia?.("(pointer: coarse)").matches;
    if (!busy && !coarsePointer) input.current?.focus();
  }, [busy, selectedTool]);
  return (
    <div className={`composer-layer ${embedded ? "is-embedded" : ""}`}>
      {toolMenuOpen && (
        <ComposerToolMenu
          availableTools={availableTools}
          onClose={() => setToolMenuOpen(false)}
          onSelect={(tool) => {
            onTool(tool);
            setToolMenuOpen(false);
          }}
        />
      )}
      {modeMenuOpen && (
        <ComposerModeMenu
          executionModes={executionModes}
          onClose={() => setModeMenuOpen(false)}
          onSelect={(mode) => {
            onExecutionMode(mode);
            setModeMenuOpen(false);
          }}
          selected={currentMode.id}
        />
      )}
      <form
        className="floating-composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <button
          aria-controls="kolibri-composer-tools"
          aria-expanded={toolMenuOpen}
          aria-label="Выбрать инструмент"
          className={toolMenuOpen ? "is-active" : ""}
          onClick={() => {
            setModeMenuOpen(false);
            setToolMenuOpen((open) => !open);
          }}
          title="Инструменты"
          type="button"
        >
          <Plus size={20} />
        </button>
        <div className="composer-input">
          {supportedModes.length > 1 ? (
            <button
              aria-controls="kolibri-execution-modes"
              aria-expanded={modeMenuOpen}
              aria-label="Выбрать режим работы"
              className="execution-mode-trigger"
              onClick={() => {
                setToolMenuOpen(false);
                setModeMenuOpen((open) => !open);
              }}
              title={`Режим работы: ${currentMode.label.toLowerCase()}`}
              type="button"
            >
              <CurrentModeIcon size={14} /><span>{currentMode.label}</span><ChevronDown size={14} />
            </button>
          ) : (
            <span className="execution-mode-static"><CurrentModeIcon size={14} /><span>{currentMode.label}</span></span>
          )}
          {selected && (
            <button className="selected-tool" onClick={() => onTool("")} type="button">
              <SelectedIcon size={14} /> <span>{selected.label}</span><X size={13} />
            </button>
          )}
          <textarea
            aria-label="Задача для Kolibri"
            disabled={busy}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              const composing = event.isComposing || event.nativeEvent?.isComposing || event.keyCode === 229;
              if (event.key === "Enter" && !event.shiftKey && !composing) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder={selected ? `Опишите задачу: ${selected.label.toLowerCase()}` : "Скажите, что нужно сделать…"}
            ref={input}
            rows={1}
            value={value}
          />
        </div>
        <button
          aria-label="Отправить"
          className="composer-send"
          disabled={busy || !value.trim()}
          title="Отправить"
          type="submit"
        >
          <ArrowUp size={20} />
        </button>
      </form>
    </div>
  );
}
