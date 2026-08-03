"use client";

import {
	useAuiState,
	unstable_useComposerInput as useComposerInput,
} from "@assistant-ui/react";
import {
	ChevronDownIcon,
	ScanSearchIcon,
	ShieldAlertIcon,
	ShieldCheckIcon,
	WandSparklesIcon,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	type DeveloperAccessMode,
	useDeveloperAgentMode,
} from "@/lib/product-chat/developer-agent-mode";
import {
	PROJECT_AUDIT_PROMPT,
	PROJECT_IMPROVEMENT_PROMPT,
} from "@/lib/product-chat/project-improvement";

const ACCESS_OPTIONS: readonly {
	mode: DeveloperAccessMode;
	title: string;
	shortTitle: string;
	description: string;
}[] = [
	{
		mode: "standard",
		title: "Dev-режим выключен",
		shortTitle: "Dev-режим",
		description: "Обычные ответы без доступа к изменению кода",
	},
	{
		mode: "auto",
		title: "Dev-режим: с подтверждением",
		shortTitle: "Dev · С подтверждением",
		description: "Агент работает с кодом, опасные действия подтверждаются",
	},
	{
		mode: "full",
		title: "Dev-режим: полный доступ",
		shortTitle: "Dev · Полный доступ",
		description: "Полный доступ к рабочей среде без подтверждений",
	},
];

export function DeveloperModeControl({
	surface = "composer",
}: {
	surface?: "composer" | "settings" | "mobile-header";
}) {
	const developerMode = useDeveloperAgentMode();
	const isRunning = useAuiState((state) => state.thread.isRunning);
	const composer = useComposerInput();
	const [open, setOpen] = useState(false);

	if (!developerMode.available) return null;

	const selected =
		ACCESS_OPTIONS.find((option) => option.mode === developerMode.mode) ??
		ACCESS_OPTIONS[0];
	const selectMode = (mode: DeveloperAccessMode) => {
		developerMode.setMode(mode);
		setOpen(false);
	};
	const prepareProjectAutopilot = (
		mode: Extract<DeveloperAccessMode, "auto" | "full">,
		prompt: string,
	) => {
		developerMode.setMode(mode);
		composer.setText(prompt);
		setOpen(false);
	};

	return (
		<DropdownMenu open={open} onOpenChange={setOpen}>
			<DropdownMenuTrigger asChild>
				<Button
					type="button"
					variant="ghost"
					disabled={isRunning}
					aria-label={`${selected.title}. Открыть выбор Dev-режима`}
					className={
						surface === "settings"
							? developerMode.mode === "full"
								? "h-11 w-full justify-between rounded-xl px-3 text-orange-600"
								: "text-muted-foreground h-11 w-full justify-between rounded-xl px-3"
							: developerMode.mode === "full"
								? "h-11 max-w-[10.5rem] min-w-0 gap-1.5 rounded-full px-2 text-orange-600 sm:h-9 sm:max-w-56 sm:px-3"
								: "text-muted-foreground h-11 max-w-[10.5rem] min-w-0 gap-1.5 rounded-full px-2 sm:h-9 sm:max-w-56 sm:px-3"
					}
				>
					{developerMode.mode === "full" ? (
						<ShieldAlertIcon className="size-4 shrink-0" aria-hidden="true" />
					) : (
						<ShieldCheckIcon className="size-4 shrink-0" aria-hidden="true" />
					)}
					<span className="min-w-0 truncate text-xs sm:text-sm">
						{selected.shortTitle}
					</span>
					<ChevronDownIcon
						className="size-3.5 shrink-0 opacity-60"
						aria-hidden="true"
					/>
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuContent
				align={surface === "settings" ? "start" : "start"}
				sideOffset={8}
				className="z-[90] w-[min(34rem,calc(100vw-1rem))] rounded-2xl p-2 shadow-xl"
			>
				<DropdownMenuLabel className="text-muted-foreground px-3 py-1 text-sm font-normal">
					Dev-режим
				</DropdownMenuLabel>
				<DropdownMenuRadioGroup value={developerMode.mode}>
					{ACCESS_OPTIONS.map((option) => (
						<DropdownMenuRadioItem
							key={option.mode}
							value={option.mode}
							onSelect={() => selectMode(option.mode)}
							className={
								option.mode === "full"
									? "min-h-14 items-start px-3 py-2 text-orange-600"
									: "min-h-14 items-start px-3 py-2"
							}
						>
							<span className="min-w-0 flex-1">
								<span className="block text-sm font-medium">
									{option.title}
								</span>
								<span className="text-muted-foreground mt-0.5 block text-xs leading-4">
									{option.description}
								</span>
							</span>
						</DropdownMenuRadioItem>
					))}
				</DropdownMenuRadioGroup>
				{surface === "composer" ? (
					<>
						<DropdownMenuSeparator />
						<DropdownMenuLabel className="text-muted-foreground px-3 py-1 text-sm font-normal">
							Автопилот проекта
						</DropdownMenuLabel>
						<DropdownMenuItem
							disabled={isRunning || composer.isDisabled}
							onSelect={() =>
								prepareProjectAutopilot("auto", PROJECT_AUDIT_PROMPT)
							}
							className="min-h-14 items-start gap-3 px-3 py-2"
						>
							<ScanSearchIcon className="mt-0.5 size-4 shrink-0" />
							<span className="min-w-0">
								<span className="block text-sm font-medium">
									Полное сканирование
								</span>
								<span className="text-muted-foreground mt-0.5 block text-xs leading-4">
									Аудит без изменения файлов, с приоритетами P0–P3
								</span>
							</span>
						</DropdownMenuItem>
						<DropdownMenuItem
							disabled={isRunning || composer.isDisabled}
							onSelect={() =>
								prepareProjectAutopilot("full", PROJECT_IMPROVEMENT_PROMPT)
							}
							className="min-h-14 items-start gap-3 px-3 py-2 text-orange-600 focus:text-orange-600"
						>
							<WandSparklesIcon className="mt-0.5 size-4 shrink-0" />
							<span className="min-w-0">
								<span className="block text-sm font-medium">
									Улучшить безопасно
								</span>
								<span className="text-muted-foreground mt-0.5 block text-xs leading-4">
									Найти и реализовать одно низкорисковое улучшение
								</span>
							</span>
						</DropdownMenuItem>
					</>
				) : null}
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
