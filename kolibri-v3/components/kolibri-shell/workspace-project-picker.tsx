"use client";

import { Check, FolderOpen } from "lucide-react";
import {
	SHELL_HEADER_ICON_BUTTON_CLASS,
	SHELL_ICON_SIZE_CLASS,
	SHELL_ICON_STROKE_WIDTH,
} from "@/components/kolibri-shell/header-design-system";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { WorkspaceProject } from "@/lib/workspace-types";
import { uiClassTokens } from "@/components/ui/class-names";

export function WorkspaceProjectPicker({
	activeProjectId,
	className,
	onProjectSelect,
	projectName,
	projects = [],
}: {
	activeProjectId?: string | null;
	className?: string;
	onProjectSelect?: (project: WorkspaceProject) => void;
	projectName?: string;
	projects?: readonly WorkspaceProject[];
}) {
	const projectLabel = projectName?.trim() || null;

	return (
		<DropdownMenu>
			<Tooltip>
				<TooltipTrigger asChild>
					<DropdownMenuTrigger asChild>
						<Button
							type="button"
							variant="ghost"
							size="icon-xs"
							className={cn(
								SHELL_HEADER_ICON_BUTTON_CLASS,
								activeProjectId && "bg-muted/65 text-foreground",
								className,
							)}
							aria-label={
								projectLabel
									? `Выбрать проект. Текущий проект: ${projectLabel}`
									: "Выбрать проект"
							}
							disabled={projects.length === 0}
						>
							<FolderOpen
								className={`${SHELL_ICON_SIZE_CLASS} shrink-0`}
								aria-hidden="true"
								strokeWidth={SHELL_ICON_STROKE_WIDTH}
							/>
							<span className="sr-only">
								{projectLabel ?? "Проект не выбран"}
							</span>
						</Button>
					</DropdownMenuTrigger>
				</TooltipTrigger>
				<TooltipContent side="bottom" sideOffset={8}>
					{projects.length === 0
						? "Проекты появятся после сохранения"
						: projectLabel
							? `Проект: ${projectLabel}`
							: "Выбрать проект"}
				</TooltipContent>
			</Tooltip>
			<DropdownMenuContent align="end" className="w-72">
				<DropdownMenuLabel className="text-xs">
					Текущий проект
				</DropdownMenuLabel>
				<DropdownMenuSeparator />
				{projects.map((project) => {
					const active = project.id === activeProjectId;
					return (
						<DropdownMenuItem
							key={project.id}
							onSelect={() => onProjectSelect?.(project)}
							className="min-h-10"
						>
							<FolderOpen
								className={`${SHELL_ICON_SIZE_CLASS} shrink-0`}
								aria-hidden="true"
								strokeWidth={SHELL_ICON_STROKE_WIDTH}
							/>
							<span className="min-w-0 flex-1">
								<span className={uiClassTokens.workspaceHeaderMenuItemMeta}>
									{project.name}
								</span>
								<span className={uiClassTokens.workspaceHeaderMenuItemSub}>
									{project.updatedAt?.trim() || `…${project.id.slice(-8)}`}
								</span>
							</span>
							{active ? (
								<Check
									className={`${SHELL_ICON_SIZE_CLASS} shrink-0`}
									aria-hidden="true"
									strokeWidth={SHELL_ICON_STROKE_WIDTH}
								/>
							) : null}
						</DropdownMenuItem>
					);
				})}
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
