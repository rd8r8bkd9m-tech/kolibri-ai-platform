import { X } from "lucide-react";

export function MobileWindowHeader({ labelId, onClose, status, title }) {
  return (
    <header>
      <div><strong id={labelId}>{title}</strong><span>{status}</span></div>
      <button aria-label="Закрыть окно" data-dialog-initial-focus onClick={onClose} type="button"><X size={19} /></button>
    </header>
  );
}
