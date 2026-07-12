import { useRef } from "react";
import { Check, Code2, Gauge, X } from "lucide-react";
import { EXECUTION_MODES } from "../app/constants";
import { useDialogFocus } from "../app/useDialogFocus";

export function ComposerModeMenu({ executionModes = [], onClose, onSelect, selected }) {
  const menu = useRef(null);
  const modes = EXECUTION_MODES.filter((mode) => executionModes.includes(mode.id));
  const current = modes.find((mode) => mode.id === selected) || modes[0] || EXECUTION_MODES[0];
  useDialogFocus(menu, { onEscape: onClose, initialFocus: "[aria-checked='true']" });

  return (
    <>
      <button aria-label="Закрыть выбор режима" className="mode-menu-scrim" onClick={onClose} type="button" />
      <div aria-label="Режим работы Kolibri" className="mode-menu" id="kolibri-execution-modes" ref={menu} role="menu" tabIndex={-1}>
        <header>
          <div><span>Kolibri</span><strong>Режим работы</strong></div>
          <button aria-label="Закрыть" onClick={onClose} type="button"><X size={18} /></button>
        </header>
        <div className="mode-menu-facts" aria-label="Параметры выбранного режима">
          <div><small>Модель</small><strong>Kolibri</strong></div>
          <div><small>Рассуждение</small><strong>{current.reasoning}</strong></div>
          <div><small>Скорость</small><strong>{current.speed}</strong></div>
        </div>
        {modes.map((mode) => {
          const ModeIcon = mode.id === "codex" ? Code2 : Gauge;
          const active = selected === mode.id;
          return (
            <button aria-checked={active} key={mode.id} onClick={() => onSelect(mode.id)} role="menuitemradio" type="button">
              <ModeIcon size={18} />
              <span><strong>{mode.label}</strong><small>{mode.hint}</small></span>
              {active ? <Check aria-hidden="true" size={17} /> : <span aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    </>
  );
}
