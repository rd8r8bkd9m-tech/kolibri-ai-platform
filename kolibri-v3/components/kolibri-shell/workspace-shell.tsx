"use client";

import { DesktopWorkspace } from "@/components/kolibri-shell/desktop-workspace/desktop-workspace";

/**
 * Desktop Next surface. The mobile product is served by the dedicated Expo
 * client at the gateway boundary, so this component deliberately owns only
 * the desktop workflow.
 */
export function WorkspaceShell() {
	return <DesktopWorkspace />;
}
