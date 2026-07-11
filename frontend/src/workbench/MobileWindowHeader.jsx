import { useEffect, useRef } from "react";
import { X } from "lucide-react";

export function MobileWindowHeader({ labelId, onClose, status, title }) {
  const closeButton = useRef(null);
  useEffect(() => {
    closeButton.current?.focus();
    const close = (event) => event.key === "Escape" && onClose();
    globalThis.addEventListener("keydown", close);
    return () => globalThis.removeEventListener("keydown", close);
  }, [onClose]);
  return (
    <header>
      <div><strong id={labelId}>{title}</strong><span>{status}</span></div>
      <button aria-label="Закрыть окно" onClick={onClose} ref={closeButton} type="button"><X size={19} /></button>
    </header>
  );
}
