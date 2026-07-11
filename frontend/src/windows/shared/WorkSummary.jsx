import { useEffect, useId, useState } from "react";
import { ChevronDown, ListChecks, X } from "lucide-react";

const KIND_LABELS = Object.freeze({
  plan: "План",
  tool: "Инструменты",
  source: "Источники",
  check: "Проверка",
  verdict: "Итог",
});

const STATUS_LABELS = Object.freeze({
  pending: "Ожидается",
  running: "Выполняется",
  passed: "Готово",
  failed: "Не пройдено",
  skipped: "Не требовалось",
  incomplete: "Частично",
  blocked: "Нужны данные",
});

function summaryState(items) {
  if (items.some((item) => item.status === "running" || item.status === "pending")) return "Выполняется";
  if (items.some((item) => item.status === "failed")) return "Есть замечания";
  if (items.some((item) => item.status === "blocked" || item.status === "incomplete")) return "Нужны данные";
  return "Проверено";
}

export function WorkSummary({ summary }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const items = Array.isArray(summary?.items)
    ? summary.items.filter((item) => KIND_LABELS[item?.kind] && STATUS_LABELS[item?.status]).slice(0, 5)
    : [];

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!items.length) return null;

  return (
    <section className={`work-summary ${open ? "is-open" : ""}`}>
      <button
        aria-controls={panelId}
        aria-expanded={open}
        className="work-summary-trigger"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <ListChecks aria-hidden="true" size={15} />
        <span>Ход работы</span>
        <small aria-live="polite">{summaryState(items)}</small>
        <ChevronDown aria-hidden="true" size={14} />
      </button>
      {open && (
        <>
          <button aria-label="Закрыть ход работы" className="work-summary-scrim" onClick={() => setOpen(false)} type="button" />
          <div aria-label="Ход работы Kolibri" className="work-summary-panel" id={panelId} role="region">
            <header>
              <div>
                <strong>Ход работы</strong>
                <span>Краткая проверяемая сводка</span>
              </div>
              <button aria-label="Закрыть" onClick={() => setOpen(false)} type="button"><X size={17} /></button>
            </header>
            <ol>
              {items.map((item) => (
                <li className={`is-${item.status}`} key={item.kind}>
                  <span aria-hidden="true" />
                  <div>
                    <strong>{KIND_LABELS[item.kind]}</strong>
                    <p>{item.detail || STATUS_LABELS[item.status]}</p>
                  </div>
                  <small>{STATUS_LABELS[item.status]}</small>
                </li>
              ))}
            </ol>
            <p className="work-summary-policy">Скрытые рассуждения, промпты, ключи и технические данные здесь не показываются.</p>
          </div>
        </>
      )}
    </section>
  );
}
