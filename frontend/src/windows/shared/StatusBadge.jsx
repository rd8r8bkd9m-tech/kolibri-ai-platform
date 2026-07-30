import { Check } from "lucide-react";

const STATUS_LABELS = Object.freeze({
  draft: "Черновик",
  running: "Выполняется",
  completed: "Готово",
  incomplete: "Нужна доработка",
  failed: "Ошибка",
});

export function StatusBadge({ status }) {
  const normalized = status || "running";
  return (
    <span className={`task-status is-${normalized}`}>
      {normalized === "completed" && <Check size={13} />}
      {STATUS_LABELS[normalized] || STATUS_LABELS.running}
    </span>
  );
}
