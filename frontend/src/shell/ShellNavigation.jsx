import { useRef } from "react";
import { useDialogFocus } from "../app/useDialogFocus";
import { ToolDock } from "./ToolDock";

export function ShellNavigation({ availableTools = [], navigation, minimizedWindows, selected, onNewProject, onRestoreWindow, onSelect, onSystem }) {
  const dock = useRef(null);
  useDialogFocus(dock, {
    open: navigation.mobile && navigation.mobileOpen,
    onEscape: navigation.dismiss,
    fallbackFocus: "#kolibri-navigation-trigger",
  });
  return <>
    <button aria-label="Закрыть навигацию" className={`navigation-scrim ${navigation.mobileOpen ? "is-visible" : ""}`} onClick={navigation.dismiss} type="button" />
    <ToolDock
      availableTools={availableTools}
      expanded={navigation.expanded}
      dockRef={dock}
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
