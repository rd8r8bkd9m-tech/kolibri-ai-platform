import { useEffect, useRef } from "react";
import { ArrowUp, Code2, Gauge, Plus, X } from "lucide-react";
import { EXECUTION_MODES, TOOLS } from "../app/constants";
import { ComposerToolMenu } from "./ComposerToolMenu";

export function Composer({
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
  const selected = TOOLS.find((item) => item.id === selectedTool);
  const SelectedIcon = selected?.icon;
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
          onClose={() => setToolMenuOpen(false)}
          onSelect={(tool) => {
            onTool(tool);
            setToolMenuOpen(false);
          }}
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
          onClick={() => setToolMenuOpen((open) => !open)}
          type="button"
        >
          <Plus size={20} />
        </button>
        <div className="composer-input">
          <div aria-label="Режим выполнения" className="execution-mode-switch" role="group">
            {EXECUTION_MODES.map((mode) => {
              const ModeIcon = mode.id === "codex" ? Code2 : Gauge;
              const supported = executionModes.includes(mode.id);
              return (
                <button
                  aria-pressed={executionMode === mode.id}
                  disabled={!supported}
                  key={mode.id}
                  onClick={() => supported && onExecutionMode(mode.id)}
                  title={supported ? mode.hint : `${mode.label} недоступен: backend не подтвердил capability`}
                  type="button"
                >
                  <ModeIcon size={13} /> {mode.label}
                </button>
              );
            })}
          </div>
          {selected && (
            <button className="selected-tool" onClick={() => onTool("")} type="button">
              <SelectedIcon size={14} /> {selected.label}<X size={13} />
            </button>
          )}
          <textarea
            aria-label="Задача для Kolibri"
            disabled={busy}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
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
          type="submit"
        >
          <ArrowUp size={20} />
        </button>
      </form>
    </div>
  );
}
