import { ToolDock } from "./ToolDock";

export function ShellNavigation({ navigation, minimizedWindows, selected, onNewProject, onRestoreWindow, onSelect, onSystem }) {
  return <>
    <button aria-label="Закрыть навигацию" className={`navigation-scrim ${navigation.mobileOpen ? "is-visible" : ""}`} onClick={navigation.dismiss} type="button" />
    <ToolDock
      expanded={navigation.expanded}
      mobile={navigation.mobile}
      mobileOpen={navigation.mobileOpen}
      minimizedWindows={minimizedWindows}
      onDismiss={navigation.dismiss}
      onNewProject={onNewProject}
      onPointerEnter={navigation.onPointerEnter}
      onPointerLeave={navigation.onPointerLeave}
      onRestoreWindow={onRestoreWindow}
      onSelect={onSelect}
      onSystem={onSystem}
      pinned={navigation.pinned}
      preview={navigation.preview}
      selected={selected}
    />
  </>;
}
