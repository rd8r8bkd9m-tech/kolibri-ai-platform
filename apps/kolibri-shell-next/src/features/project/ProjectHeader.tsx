import { OverlayDialog } from "@components/OverlayDialog";
import type { ProjectSummary, RuntimeStatus } from "@domain/shell";
import { Check, ChevronDown, Clock3, Info, Menu, MoreHorizontal, RotateCw } from "lucide-react";
import { useState } from "react";

interface ProjectHeaderProps {
  project: ProjectSummary;
  runtimeStatus: RuntimeStatus;
  onRetry: () => void;
  onNotice: (message: string) => void;
}

const statusLabel: Record<RuntimeStatus, string> = {
  connecting: "Подключение…",
  ready: "Kolibri подключён",
  unavailable: "Kolibri недоступен",
};

export function ProjectHeader({ project, runtimeStatus, onRetry, onNotice }: ProjectHeaderProps) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <>
      <header className="shell-header">
        <button
          className={`bird-menu-slot ${navigationOpen ? "is-open" : ""}`}
          type="button"
          aria-label={navigationOpen ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={navigationOpen}
          onClick={() => setNavigationOpen((open) => !open)}
        >
          <img src="/kolibri-bird.png" alt="" className="bird-menu-image" />
          <Menu aria-hidden="true" className="bird-menu-icon" />
        </button>

        <div className="project-selector-wrap">
          <button
            className="project-selector"
            type="button"
            aria-expanded={projectOpen}
            onClick={() => setProjectOpen((open) => !open)}
          >
            <span>{project.title}</span>
            {project.location ? <span className="project-location">·&nbsp; {project.location}</span> : null}
            <ChevronDown aria-hidden="true" />
          </button>
          {projectOpen ? (
            <div className="header-popover project-popover" role="menu">
              <p className="popover-kicker">Текущий проект</p>
              <button type="button" role="menuitem" onClick={() => setProjectOpen(false)}>
                <span>
                  <strong>{project.title}</strong>
                  <small>{project.location || "Без локации"}</small>
                </span>
                <Check aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </div>

        <div className="header-actions">
          <button className="header-button" type="button" onClick={() => setHistoryOpen(true)}>
            <Clock3 aria-hidden="true" />
            <span>История</span>
          </button>
          <div className="more-wrap">
            <button
              className="header-button icon-only"
              type="button"
              aria-label="Ещё"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((open) => !open)}
            >
              <MoreHorizontal aria-hidden="true" />
            </button>
            {moreOpen ? (
              <div className="header-popover more-popover" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onNotice(statusLabel[runtimeStatus]);
                    setMoreOpen(false);
                  }}
                >
                  <Info aria-hidden="true" />
                  Состояние
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onRetry();
                    setMoreOpen(false);
                  }}
                >
                  <RotateCw aria-hidden="true" />
                  Переподключить
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <OverlayDialog
        open={navigationOpen}
        title="Kolibri"
        onClose={() => setNavigationOpen(false)}
        className="navigation-dialog"
      >
        <p className="navigation-label">Главный чат</p>
        <button className="navigation-current" type="button" onClick={() => setNavigationOpen(false)}>
          <span>{project.title}</span>
          <small>{project.location}</small>
        </button>
        <div className={`runtime-chip runtime-${runtimeStatus}`}>{statusLabel[runtimeStatus]}</div>
      </OverlayDialog>

      <OverlayDialog open={historyOpen} title="История" onClose={() => setHistoryOpen(false)}>
        <div className="history-list">
          <button type="button" className="history-item" onClick={() => setHistoryOpen(false)}>
            <span>Предварительная смета</span>
            <small>Сегодня · текущий чат</small>
          </button>
          <p>В Kolibri один непрерывный чат для этого проекта.</p>
        </div>
      </OverlayDialog>
    </>
  );
}
