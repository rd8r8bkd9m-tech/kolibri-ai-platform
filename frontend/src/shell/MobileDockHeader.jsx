import { X } from "lucide-react";

export function MobileDockHeader({ open, onClose }) {
  return (
    <header className="dock-mobile-header">
      <div><strong>Kolibri AI</strong><span>Рабочие пространства</span></div>
      <button aria-label="Закрыть навигацию" data-dialog-initial-focus={open || undefined} onClick={onClose} type="button"><X size={19} /></button>
    </header>
  );
}
