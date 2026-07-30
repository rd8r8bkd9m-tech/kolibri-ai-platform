import { useEffect } from "react";
import { ChevronRight, History, X } from "lucide-react";

export function HistoryDrawer({ items, open, onClose, onOpen }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && onClose();
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="drawer-layer">
      <button aria-label="Закрыть историю" className="drawer-scrim" onClick={onClose} type="button" />
      <aside aria-modal="true" className="history-drawer" role="dialog">
        <header>
          <div><span>Проекты</span><h2>Продолжить работу</h2></div>
          <button aria-label="Закрыть" onClick={onClose} type="button"><X size={20} /></button>
        </header>
        <div className="history-list">
          {items.length ? items.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onOpen(item);
                onClose();
              }}
              type="button"
            >
              <span><strong>{item.title}</strong><small>{new Date(item.createdAt).toLocaleString("ru-RU")}</small></span>
              <ChevronRight size={17} />
            </button>
          )) : (
            <div className="history-empty">
              <History size={26} />
              <strong>История пока пуста</strong>
              <p>Результаты появятся здесь после выполнения задач.</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
