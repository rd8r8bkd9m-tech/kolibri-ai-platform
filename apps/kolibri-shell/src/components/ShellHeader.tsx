import { ChevronDown, History, MoreHorizontal, MessageSquarePlus } from 'lucide-react';
import { useState } from 'react';
import { MascotMenuButton } from './MascotMenuButton';

interface ShellHeaderProps {
  presentation: 'mobile' | 'desktop';
  projectTitle: string;
  historyOpen: boolean;
  onToggleHistory(): void;
  onNewConversation(): void;
}

export function ShellHeader({
  presentation,
  projectTitle,
  historyOpen,
  onToggleHistory,
  onNewConversation,
}: ShellHeaderProps) {
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <header className="system-bar" data-presentation={presentation}>
      <MascotMenuButton open={historyOpen} onToggle={onToggleHistory} />

      <button className="project-selector" type="button" onClick={onToggleHistory}>
        <span>{projectTitle}</span>
        <ChevronDown aria-hidden="true" />
      </button>

      {presentation === 'desktop' ? (
        <div className="header-actions">
          <button className="history-button" type="button" onClick={onToggleHistory}>
            <History aria-hidden="true" />
            История
          </button>
          <div className="header-more-anchor">
            <button
              className="header-more-button"
              type="button"
              aria-label="Ещё"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((value) => !value)}
            >
              <MoreHorizontal aria-hidden="true" />
            </button>
            {moreOpen ? (
              <div className="header-more-menu" role="menu">
                <button type="button" role="menuitem" onClick={() => { onNewConversation(); setMoreOpen(false); }}>
                  <MessageSquarePlus aria-hidden="true" />
                  Новый диалог
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </header>
  );
}
