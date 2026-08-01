"use client";

import { useAuiState } from "@assistant-ui/react";
import {
	ChevronDownIcon,
	ShieldAlertIcon,
	ShieldCheckIcon,
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
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	type DeveloperAccessMode,
	useDeveloperAgentMode,
} from "@/lib/product-chat/developer-agent-mode";

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
	const [open, setOpen] = useState(false);

	if (!developerMode.available) return null;

	const selected =
		ACCESS_OPTIONS.find((option) => option.mode === developerMode.mode) ??
		ACCESS_OPTIONS[0];
	const selectMode = (mode: DeveloperAccessMode) => {
		developerMode.setMode(mode);
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
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
