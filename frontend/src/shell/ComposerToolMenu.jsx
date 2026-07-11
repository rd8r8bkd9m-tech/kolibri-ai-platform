import { useEffect } from "react";
import { ChevronRight, X } from "lucide-react";
import { TOOLS } from "../app/constants";

export function ComposerToolMenu({ onClose, onSelect }) {
  useEffect(() => {
    const close = (event) => event.key === "Escape" && onClose();
    globalThis.addEventListener("keydown", close);
    return () => globalThis.removeEventListener("keydown", close);
  }, [onClose]);
  return (
    <>
      <button aria-label="Закрыть выбор инструмента" className="tool-menu-scrim" onClick={onClose} type="button" />
      <div aria-label="Инструменты Kolibri" className="tool-menu" id="kolibri-composer-tools" role="menu">
        <header>
          <div><span>Kolibri Canvas</span><strong>Что создать?</strong></div>
          <button aria-label="Закрыть" onClick={onClose} type="button"><X size={18} /></button>
        </header>
        {TOOLS.map((tool) => {
          const ToolIcon = tool.icon;
          return (
            <button key={tool.id} onClick={() => onSelect(tool.id)} role="menuitem" type="button">
              <ToolIcon size={18} />
              <span><strong>{tool.label}</strong><small>{tool.hint}</small></span>
              <ChevronRight size={16} />
            </button>
          );
        })}
      </div>
    </>
  );
}
