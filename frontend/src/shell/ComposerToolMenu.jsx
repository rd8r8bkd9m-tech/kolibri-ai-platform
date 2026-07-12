import { useRef } from "react";
import { ChevronRight, X } from "lucide-react";
import { useDialogFocus } from "../app/useDialogFocus";

export function ComposerToolMenu({ availableTools = [], onClose, onSelect }) {
  const menu = useRef(null);
  useDialogFocus(menu, { onEscape: onClose, initialFocus: "[role='menuitem']" });
  return (
    <>
      <button aria-label="Закрыть выбор инструмента" className="tool-menu-scrim" onClick={onClose} type="button" />
      <div aria-label="Инструменты Kolibri" className="tool-menu" id="kolibri-composer-tools" ref={menu} role="menu" tabIndex={-1}>
        <header>
          <div><span>Kolibri Canvas</span><strong>Что создать?</strong></div>
          <button aria-label="Закрыть" onClick={onClose} type="button"><X size={18} /></button>
        </header>
        {availableTools.map((tool) => {
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
