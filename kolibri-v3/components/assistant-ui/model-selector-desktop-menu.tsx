"use client";

import type { SelectorMenuProps } from "@/components/assistant-ui/model-selector-controls";
import {
	EffortItems,
	ModelItems,
	SpeedItems,
} from "@/components/assistant-ui/model-selector-items";
import {
	compactModelName,
	EFFORT_NAMES,
	serviceTierName,
} from "@/components/assistant-ui/model-selector-utils";
import {
	DropdownMenuItem,
	DropdownMenuSeparator,
	DropdownMenuSub,
	DropdownMenuSubContent,
	DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import { openModelSettings } from "@/lib/workspace-events";

export function DesktopSelectorMenu(props: SelectorMenuProps) {
	const effortName = props.selectedEffort
		? (EFFORT_NAMES[props.selectedEffort] ?? props.selectedEffort)
		: "—";
	const selectedTier = props.selectedModel?.serviceTiers.find(
		(tier) => tier.id === props.selectedServiceTier,
	);

	return (
		<>
			<DropdownMenuSub>
				<DropdownMenuSubTrigger className="min-h-11 px-3 text-[15px]">
					<span>Модель</span>
					<span className="text-muted-foreground ml-auto max-w-32 truncate">
						{props.selectedModel
							? compactModelName(props.selectedModel.displayName)
							: "—"}
					</span>
				</DropdownMenuSubTrigger>
				<DropdownMenuSubContent
					sideOffset={8}
					className="z-[90] w-72 rounded-2xl p-1.5"
				>
					<ModelItems
						models={props.models}
						selectedModelId={props.selectedModelId}
						disabled={props.disabled}
						onModelSelect={props.onModelSelect}
					/>
				</DropdownMenuSubContent>
			</DropdownMenuSub>
			<DropdownMenuSub>
				<DropdownMenuSubTrigger
					disabled={
						!props.selectedModel ||
						props.selectedModel.supportedReasoningEfforts.length === 0
					}
					className="min-h-11 px-3 text-[15px]"
				>
					<span>Усилие</span>
					<span className="text-muted-foreground ml-auto max-w-36 truncate">
						{effortName}
					</span>
				</DropdownMenuSubTrigger>
				<DropdownMenuSubContent
					sideOffset={8}
					className="z-[90] w-80 rounded-2xl p-1.5"
				>
					<EffortItems
						selectedModel={props.selectedModel}
						selectedEffort={props.selectedEffort}
						disabled={props.disabled}
						onEffortSelect={props.onEffortSelect}
					/>
				</DropdownMenuSubContent>
			</DropdownMenuSub>
			<DropdownMenuSub>
				<DropdownMenuSubTrigger
					disabled={!props.selectedModel?.serviceTiers.length}
					className="min-h-11 px-3 text-[15px]"
				>
					<span>Скорость</span>
					<span className="text-muted-foreground ml-auto max-w-28 truncate">
						{serviceTierName(selectedTier)}
					</span>
				</DropdownMenuSubTrigger>
				<DropdownMenuSubContent
					sideOffset={8}
					className="z-[90] w-80 rounded-2xl p-1.5"
				>
					<SpeedItems
						selectedModel={props.selectedModel}
						selectedServiceTier={props.selectedServiceTier}
						disabled={props.disabled}
						onServiceTierSelect={props.onServiceTierSelect}
					/>
				</DropdownMenuSubContent>
			</DropdownMenuSub>
			<DropdownMenuSeparator />
			<DropdownMenuItem
				onSelect={() => openModelSettings()}
				className="text-muted-foreground min-h-10 px-3 text-[15px]"
			>
				Модели и подключения
			</DropdownMenuItem>
		</>
	);
}
