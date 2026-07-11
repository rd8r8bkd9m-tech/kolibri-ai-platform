import { SYSTEM_APPS, TOOLS } from "../app/constants";
import { SquarePen } from "lucide-react";
import { MobileDockHeader } from "./MobileDockHeader";
import { MinimizedWindows } from "./MinimizedWindows";

export function ToolDock({ expanded, mobile, mobileOpen, pinned, preview, minimizedWindows, selected, onDismiss, onNewProject, onPointerEnter, onPointerLeave, onRestoreWindow, onSelect, onSystem }) {
  const act = (callback) => () => {
    callback();
    onDismiss?.();
  };
  return (
    <aside
      aria-hidden={mobile && !mobileOpen}
      aria-label="Навигация Kolibri"
      aria-modal={mobileOpen || undefined}
      className={`tool-dock ${expanded ? "is-expanded" : ""} ${pinned ? "is-pinned" : ""} ${preview ? "is-preview" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}
      id="kolibri-navigation"
      inert={mobile && !mobileOpen}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      role={mobile ? "dialog" : undefined}
    >
      <MobileDockHeader onClose={onDismiss} open={mobileOpen} />
      <div className="dock-context"><strong>Рабочее пространство</strong><span>{pinned ? "Закреплено" : "Навигация"}</span></div>
      <button aria-label="Новый проект" className="dock-new-project" onClick={act(onNewProject)} title="Новый проект" type="button">
        <SquarePen size={19} /><span>Новый проект</span>
      </button>
      {expanded && <small className="dock-section-label">Создать</small>}
      {TOOLS.map((tool) => {
        const ToolIcon = tool.icon;
        return (
          <button
            aria-label={tool.label}
            className={selected === tool.id ? "is-selected" : ""}
            key={tool.id}
            onClick={act(() => onSelect(tool.id))}
            title={tool.label}
            type="button"
          >
            <ToolIcon size={19} />
            <span>{tool.label}</span>
          </button>
        );
      })}
      <span className="dock-spacer" />
      <MinimizedWindows expanded={expanded} onRestore={(id) => { onRestoreWindow(id); onDismiss?.(); }} windows={minimizedWindows} />
      {expanded && <small className="dock-section-label">Система</small>}
      {SYSTEM_APPS.map((app) => {
        const AppIcon = app.icon;
        return (
          <button
            aria-label={app.label}
            key={app.id}
            onClick={act(() => onSystem(app.id))}
            title={app.label}
            type="button"
          >
            <AppIcon size={19} />
            <span>{app.label}</span>
          </button>
        );
      })}
    </aside>
  );
}
