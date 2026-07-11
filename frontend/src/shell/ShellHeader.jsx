import { History, Layers3, ServerCog, SquarePen } from "lucide-react";
import { SystemBar } from "./SystemBar";

export function ShellHeader({ navigation, projectCount, title, onNewProject, onOpenProjects, onRestoreWindows }) {
  return (
    <SystemBar
      brandLabel={navigation.mobile
        ? (navigation.mobileOpen ? "Закрыть навигацию Kolibri" : "Открыть навигацию Kolibri")
        : (navigation.pinned ? "Свернуть навигацию Kolibri" : "Закрепить навигацию Kolibri")}
      navigationOpen={navigation.expanded}
      onBrandActivate={navigation.toggle}
      onBrandPreviewEnter={navigation.onPointerEnter}
      onBrandPreviewLeave={navigation.onPointerLeave}
      subtitle="Kolibri AI OS"
      title={title}
    >
      <button aria-label="История проектов" className="desktop-history-action" onClick={onOpenProjects} type="button">
        <History size={18} /><span>История</span>{projectCount > 0 && <b>{projectCount}</b>}
      </button>
      <button aria-label="Новый проект" className="new-project-action" onClick={onNewProject} type="button"><SquarePen size={18} /></button>
      <button aria-label="Восстановить окна" className="desktop-only-action" onClick={onRestoreWindows} type="button"><Layers3 size={18} /></button>
      <a aria-label="Control Center" href="/control"><ServerCog size={18} /></a>
    </SystemBar>
  );
}
