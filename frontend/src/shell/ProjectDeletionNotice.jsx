import { X } from "lucide-react";

export function ProjectDeletionNotice({ deletion, onDismiss, onUndo }) {
  if (!deletion?.project) return null;
  return (
    <aside className="project-deletion-notice" aria-label="Удалённый проект">
      <span aria-live="polite">Проект «{deletion.project.title}» удалён из истории.</span>
      <button className="project-undo" onClick={onUndo} type="button">Отменить</button>
      <button aria-label="Скрыть уведомление" onClick={onDismiss} type="button"><X size={17} /></button>
    </aside>
  );
}
