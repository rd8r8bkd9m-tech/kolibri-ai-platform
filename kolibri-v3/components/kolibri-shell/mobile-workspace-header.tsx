"use client";

import { ThreadListPrimitive } from "@assistant-ui/react";
import {
	Check,
	ChevronDown,
	ChevronLeft,
	MessageCircle,
	Plus,
} from "lucide-react";
import {
	CHAT_DESTINATION_LABEL,
	CHAT_DESTINATIONS,
	CHAT_THREAD_FALLBACK_TITLE,
	type PrimarySurface,
	SHELL_ICON_LARGE_SIZE_CLASS,
	SHELL_ICON_SIZE_CLASS,
	SHELL_ICON_STROKE_WIDTH,
	SHELL_MOBILE_HEADER_DROPDOWN_BUTTON_CLASS,
	SHELL_MOBILE_HEADER_GHOST_CLASS,
	SHELL_MOBILE_HEADER_TITLE_CLASS,
} from "@/components/kolibri-shell/header-design-system";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { uiClassTokens } from "@/components/ui/class-names";

type MobileWorkspaceHeaderProps = {
	navigationOpen?: boolean;
	activeDestination?: PrimarySurface;
	onBack?: () => void;
	onOpenChat?: () => void;
	onOpenDestination?: (destination: PrimarySurface) => void;
	onToggleNavigation: () => void;
	title?: string;
};

export function MobileWorkspaceHeader({
	navigationOpen = false,
	activeDestination = "chat",
	onBack,
	onOpenChat,
	onOpenDestination,
	onToggleNavigation,
	title = CHAT_THREAD_FALLBACK_TITLE,
}: MobileWorkspaceHeaderProps) {
	const isChat = activeDestination === "chat";
	const isProjects = activeDestination === "projects";

	return (
		<header
			data-slot="kolibri-mobile-header"
			className={uiClassTokens.mobileHeaderRoot}
		>
			<div className={uiClassTokens.mobileHeaderContainer}>
				{onBack ? (
					<Button
						type="button"
						variant="ghost"
						size="icon"
						onClick={onBack}
						aria-label="На основной экран"
						data-slot="mobile-editor-back"
						className={SHELL_MOBILE_HEADER_GHOST_CLASS}
					>
						<ChevronLeft
							aria-hidden="true"
							className={`${SHELL_ICON_LARGE_SIZE_CLASS} -translate-x-px`}
							strokeWidth={SHELL_ICON_STROKE_WIDTH}
						/>
					</Button>
				) : navigationOpen ? (
					<span aria-hidden="true" className={uiClassTokens.mobileHeaderSpacer} />
				) : (
					<Button
						type="button"
						variant="ghost"
						size="icon"
						onClick={onToggleNavigation}
						aria-label="Открыть меню"
						aria-controls="workspace-project-navigation"
						aria-expanded={navigationOpen}
						className={SHELL_MOBILE_HEADER_GHOST_CLASS}
					>
						<span
							data-slot="mobile-hamburger-icon"
							aria-hidden="true"
							className={uiClassTokens.mobileHeaderHamburger}
						>
							<span className={uiClassTokens.mobileHeaderHamburgerBar} />
							<span className={uiClassTokens.mobileHeaderHamburgerBar} />
						</span>
					</Button>
				)}

				{isChat && !onBack && onOpenDestination ? (
					<DropdownMenu>
						<DropdownMenuTrigger asChild>
							<button
								type="button"
								className={SHELL_MOBILE_HEADER_DROPDOWN_BUTTON_CLASS}
								aria-label={`${CHAT_DESTINATION_LABEL}. Выбрать раздел`}
							>
								<span>{CHAT_DESTINATION_LABEL}</span>
								<ChevronDown
									aria-hidden="true"
									className={`text-muted-foreground ${SHELL_ICON_SIZE_CLASS}`}
									strokeWidth={SHELL_ICON_STROKE_WIDTH}
								/>
							</button>
						</DropdownMenuTrigger>
						<DropdownMenuContent
							align="center"
							sideOffset={8}
							className={uiClassTokens.mobileHeaderDropdownContent}
						>
							{CHAT_DESTINATIONS.map((destination) => (
								<DropdownMenuItem
									key={destination.id}
									onSelect={() => onOpenDestination?.(destination.id)}
									className={uiClassTokens.mobileHeaderDropdownItem}
								>
									<span className={uiClassTokens.mobileHeaderDropdownLabel}>
										{destination.label}
									</span>
									{destination.id === activeDestination ? (
										<Check
											aria-hidden="true"
											className={SHELL_ICON_SIZE_CLASS}
											strokeWidth={SHELL_ICON_STROKE_WIDTH}
										/>
									) : null}
								</DropdownMenuItem>
							))}
						</DropdownMenuContent>
					</DropdownMenu>
				) : (
					<h1 className={SHELL_MOBILE_HEADER_TITLE_CLASS}>{title}</h1>
				)}

				{onBack ? (
					<span aria-hidden="true" className={uiClassTokens.mobileHeaderSpacer} />
				) : isChat || isProjects ? (
					<ThreadListPrimitive.New asChild>
						<Button
							type="button"
							variant="ghost"
							size="icon"
							aria-label={isProjects ? "Новая задача" : "Новый чат"}
							onClick={isProjects ? onOpenChat : undefined}
							className={SHELL_MOBILE_HEADER_GHOST_CLASS}
						>
							{isProjects ? (
								<Plus
									aria-hidden="true"
									className={SHELL_ICON_LARGE_SIZE_CLASS}
									strokeWidth={SHELL_ICON_STROKE_WIDTH}
								/>
							) : (
								<MessageCircle
									aria-hidden="true"
									className={SHELL_ICON_LARGE_SIZE_CLASS}
									strokeWidth={SHELL_ICON_STROKE_WIDTH}
								/>
							)}
						</Button>
					</ThreadListPrimitive.New>
				) : (
					<span aria-hidden="true" className={uiClassTokens.mobileHeaderSpacer} />
				)}
			</div>
		</header>
	);
}
