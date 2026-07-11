import { useEffect, useRef } from "react";
import { X } from "lucide-react";

export function MobileDockHeader({ open, onClose }) {
  const closeButton = useRef(null);
  useEffect(() => { if (open) closeButton.current?.focus(); }, [open]);
  return (
    <header className="dock-mobile-header">
      <div><strong>Kolibri AI</strong><span>Рабочие пространства</span></div>
      <button aria-label="Закрыть навигацию" onClick={onClose} ref={closeButton} type="button"><X size={19} /></button>
    </header>
  );
}
