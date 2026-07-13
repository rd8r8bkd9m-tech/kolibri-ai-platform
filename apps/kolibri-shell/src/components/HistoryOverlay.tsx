import { Clock3, MessageSquarePlus, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { ProjectSummary } from '../api/types';

interface HistoryOverlayProps {
  open: boolean;
  presentation: 'mobile' | 'desktop';
  projects: ProjectSummary[];
  activeProjectId?: string;
  onClose(): void;
  onNewConversation(): void;
  onSelectProject(project: ProjectSummary): void;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || date.getTime() === 0) return '';
  return new Intl.DateTimeFormat('ru', { day: 'numeric', month: 'short' }).format(date);
}

export function HistoryOverlay({
  open,
  presentation,
  projects,
  activeProjectId,
  onClose,
  onNewConversation,
  onSelectProject,
}: HistoryOverlayProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', keydown);
    return () => {
      window.removeEventListener('keydown', keydown);
      previous?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="history-overlay" role="presentation">
      <button className="history-backdrop" type="button" aria-label="Закрыть историю" onClick={onClose} />
      <aside
        className="history-panel"
        aria-label="История проектов"
        aria-modal="true"
        role="dialog"
        data-presentation={presentation === 'mobile' ? 'sheet' : 'drawer'}
      >
        <header className="history-header">
          <div>
            <span className="eyebrow">Рабочее пространство</span>
            <h2>История</h2>
          </div>
          <button ref={closeRef} className="icon-button" type="button" aria-label="Закрыть" onClick={onClose}>
            <X aria-hidden="true" />
          </button>
        </header>

        <button className="new-conversation-button" type="button" onClick={onNewConversation}>
          <MessageSquarePlus aria-hidden="true" />
          Новый диалог
        </button>

        <div className="history-list" aria-live="polite">
          {projects.length ? (
            projects.map((project) => (
              <button
                className={`history-item${project.id === activeProjectId ? ' is-active' : ''}`}
                type="button"
                key={project.id}
                onClick={() => onSelectProject(project)}
              >
                <span>{project.title}</span>
                <time>{formatDate(project.updatedAt)}</time>
              </button>
            ))
          ) : (
            <div className="history-empty">
              <Clock3 aria-hidden="true" />
              <p>Здесь появятся ваши реальные проекты.</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
