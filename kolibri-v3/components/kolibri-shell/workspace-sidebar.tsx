"use client";

import { SidebarBrand } from "@/components/kolibri-shell/sidebar/sidebar-brand";
import { SidebarChrome } from "@/components/kolibri-shell/sidebar/sidebar-chrome";
import { WorkspaceSidebarNavigation } from "@/components/kolibri-shell/sidebar/workspace-sidebar-navigation";
import { WorkspaceSidebarProfileFooter } from "@/components/kolibri-shell/sidebar/workspace-sidebar-profile-footer";
import { WorkspaceSidebarShell } from "@/components/ui/shared-wrappers";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
	type ProjectContentSection,
	WORKSPACE_PROJECTS,
	type WorkspaceSidebarProps,
} from "./sidebar/constants";

export type { ProjectContentSection, WorkspaceSidebarProps };
export { WORKSPACE_PROJECTS };

export function WorkspaceSidebar({
	activeDestination = "chat",
	className,
	isOverlay = false,
	closeOnThreadSelect = true,
	onOpenChat,
	onOpenDocuments,
	onOpenAiModels,
	onOpenProfileSettings,
	onOpenProjects,
	onOpenReferenceCatalog,
	onRequestClose,
}: WorkspaceSidebarProps) {
	return (
		<TooltipProvider>
			<WorkspaceSidebarShell
				aria-label="Навигация рабочего пространства"
				data-overlay={isOverlay ? "true" : "false"}
				className={className}
			>
				<SidebarChrome isOverlay={isOverlay} onRequestClose={onRequestClose} />
				<SidebarBrand />

				<WorkspaceSidebarNavigation
					activeDestination={activeDestination}
					isOverlay={isOverlay}
					closeOnThreadSelect={closeOnThreadSelect}
					onOpenChat={onOpenChat}
					onOpenDocuments={onOpenDocuments}
					onOpenProjects={onOpenProjects}
					onOpenReferenceCatalog={onOpenReferenceCatalog}
					onRequestClose={onRequestClose}
				/>

				<WorkspaceSidebarProfileFooter
					onOpenAiModels={onOpenAiModels}
					onOpenProfileSettings={onOpenProfileSettings}
				/>
			</WorkspaceSidebarShell>
		</TooltipProvider>
	);
}
