import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

interface OverlayDialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
}

export function OverlayDialog({ open, title, children, onClose, className = "" }: OverlayDialogProps) {
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("dialog-open");
    closeButton.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("dialog-open");
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="dialog-layer">
      <button className="dialog-backdrop" aria-label="Закрыть" onClick={onClose} type="button" />
      <section className={`dialog-panel ${className}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="dialog-header">
          <h2>{title}</h2>
          <button ref={closeButton} className="icon-button" type="button" onClick={onClose} aria-label="Закрыть">
            <X aria-hidden="true" />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
