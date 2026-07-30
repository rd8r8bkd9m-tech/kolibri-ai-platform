import { useId, useRef, useState } from "react";
import { ChevronDown, ListChecks, LoaderCircle, RotateCcw, X } from "lucide-react";
import { useDialogFocus } from "../../app/useDialogFocus";

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
  available: "Подключено",
  incomplete: "Частично",
  blocked: "Нужны данные",
});

function sourceDate(source) {
  const parts = [];
  if (source.price_level_date) parts.push(`уровень цен ${source.price_level_date}`);
  if (source.captured_at) parts.push(`получено ${source.captured_at}`);
  return parts.join(" · ");
}

function durationLabel(startedAt, completedAt) {
  const started = Date.parse(String(startedAt || ""));
  const completed = Date.parse(String(completedAt || ""));
  if (!Number.isFinite(started) || !Number.isFinite(completed) || completed < started) return "Работа завершена";
  const seconds = Math.max(1, Math.round((completed - started) / 1000));
  return `Работал ${seconds} сек.`;
}

function workStatus({ completedAt, items, progressText, recoverable, startedAt, status }) {
  if (recoverable) return { active: false, label: "Ответ прерван", meta: "Можно повторить" };
  const activeItem = items.find((item) => item.status === "running")
    || items.find((item) => item.status === "pending");
  if (["pending", "running"].includes(status) || activeItem) {
    return {
      active: true,
      label: progressText || activeItem?.detail || "Выполняю задачу",
      meta: "В работе",
    };
  }
  if (status === "failed" || items.some((item) => item.status === "failed")) {
    return { active: false, label: "Работа завершилась с замечанием", meta: "Проверьте детали" };
  }
  if (status === "incomplete" || items.some((item) => ["blocked", "incomplete"].includes(item.status))) {
    return { active: false, label: "Нужны данные для продолжения", meta: "Частично" };
  }
  if (status === "cancelled") return { active: false, label: "Запрос отменён", meta: "Можно повторить" };
  if (!status && items.length && items.every((item) => ["available", "skipped"].includes(item.status))) {
    return { active: false, label: "Подключено", meta: "" };
  }
  return { active: false, label: durationLabel(startedAt, completedAt), meta: "" };
}

export function WorkSummary({
  completedAt = "",
  defaultOpen = false,
  onRetry,
  progressText = "",
  recoverable = false,
  startedAt = "",
  status = "",
  summary,
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panel = useRef(null);
  const panelId = useId();
  const titleId = `${panelId}-title`;
  const items = Array.isArray(summary?.items)
    ? summary.items.filter((item) => KIND_LABELS[item?.kind] && STATUS_LABELS[item?.status]).slice(0, 5)
    : [];
  const state = workStatus({ completedAt, items, progressText, recoverable, startedAt, status });
  const visible = items.length > 0 || recoverable || Boolean(status);

  useDialogFocus(panel, { open, onEscape: () => setOpen(false) });

  if (!visible) return null;

  return (
    <section className={`work-summary ${state.active ? "is-active" : ""} ${recoverable ? "is-recoverable" : ""} ${open ? "is-open" : ""}`}>
      <div className="work-summary-status">
        <button
          aria-controls={panelId}
          aria-expanded={open}
          className="work-summary-trigger"
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          {state.active
            ? <LoaderCircle aria-hidden="true" className="work-summary-spinner" size={15} />
            : <ListChecks aria-hidden="true" size={15} />}
          <span aria-live="polite">{state.label}</span>
          {!!state.meta && <small>{state.meta}</small>}
          <ChevronDown aria-hidden="true" size={14} />
        </button>
        {recoverable && typeof onRetry === "function" && (
          <button className="work-summary-retry" onClick={onRetry} type="button">
            <RotateCcw aria-hidden="true" size={14} /> Повторить
          </button>
        )}
      </div>
      {open && (
        <>
          <button aria-label="Закрыть сводку работы" className="work-summary-scrim" onClick={() => setOpen(false)} type="button" />
          <div aria-labelledby={titleId} aria-modal="true" className="work-summary-panel" id={panelId} ref={panel} role="dialog" tabIndex={-1}>
            <header>
              <div>
                <strong id={titleId}>Что сделал Kolibri</strong>
                <span>Краткая проверяемая сводка без скрытых рассуждений</span>
              </div>
              <button aria-label="Закрыть" onClick={() => setOpen(false)} type="button"><X size={17} /></button>
            </header>
            {recoverable && <p className="work-summary-recovery-note">Запрос не завершился, но диалог и проект сохранены. Повтор запускает тот же запрос без дублирования сообщения.</p>}
            {!!items.length && (
              <ol>
                {items.map((item) => (
                  <li className={`is-${item.status}`} key={item.kind}>
                    <span aria-hidden="true" />
                    <div>
                      <strong>{KIND_LABELS[item.kind]}</strong>
                      <p>{item.detail || STATUS_LABELS[item.status]}</p>
                      {!!item.sources?.length && (
                        <div className="work-summary-sources" aria-label="Использованные источники">
                          {item.sources.map((source) => (
                            <a href={source.url} key={source.url} rel="noreferrer" target="_blank">
                              <span>{source.domain}</span>
                              <code>{source.url}</code>
                              {!!sourceDate(source) && <small>{sourceDate(source)}</small>}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                    <small>{STATUS_LABELS[item.status]}</small>
                  </li>
                ))}
              </ol>
            )}
            <p className="work-summary-policy">Скрытые рассуждения, промпты, ключи и технические данные здесь не показываются.</p>
          </div>
        </>
      )}
    </section>
  );
}
