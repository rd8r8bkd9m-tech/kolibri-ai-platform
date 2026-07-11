import { SYSTEM_APPS, TOOLS } from "../app/constants";
import { Menu, PanelLeftClose, SquarePen } from "lucide-react";
import { MinimizedWindows } from "./MinimizedWindows";

export function ToolDock({ expanded, minimizedWindows, selected, onExpanded, onNewProject, onRestoreWindow, onSelect, onSystem }) {
  return (
    <aside aria-label="Инструменты Kolibri" className={`tool-dock ${expanded ? "is-expanded" : ""}`}>
      <button aria-label={expanded ? "Свернуть меню" : "Открыть меню"} className="dock-toggle" onClick={() => onExpanded(!expanded)} title="Меню" type="button">
        {expanded ? <PanelLeftClose size={19} /> : <Menu size={19} />}
        <span>Kolibri OS</span>
      </button>
      <button aria-label="Новый проект" className="dock-new-project" onClick={onNewProject} title="Новый проект" type="button">
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
            onClick={() => onSelect(tool.id)}
            title={tool.label}
            type="button"
          >
            <ToolIcon size={19} />
            <span>{tool.label}</span>
          </button>
        );
      })}
      <span className="dock-spacer" />
      <MinimizedWindows expanded={expanded} onRestore={onRestoreWindow} windows={minimizedWindows} />
      {expanded && <small className="dock-section-label">Система</small>}
      {SYSTEM_APPS.map((app) => {
        const AppIcon = app.icon;
        return (
          <button
            aria-label={app.label}
            key={app.id}
            onClick={() => onSystem(app.id)}
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
