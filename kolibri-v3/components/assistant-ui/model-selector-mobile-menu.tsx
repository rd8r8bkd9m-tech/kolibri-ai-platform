"use client";

import type {
	MobilePage,
	SelectorMenuProps,
} from "@/components/assistant-ui/model-selector-controls";
import {
	EffortItems,
	keepMenuOpen,
	ModelItems,
	ModelNavigatorHeader,
	ModelNavigatorRow,
	SpeedItems,
} from "@/components/assistant-ui/model-selector-items";
import {
	EFFORT_NAMES,
	serviceTierName,
} from "@/components/assistant-ui/model-selector-utils";
import {
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
	DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

export function MobileSelectorMenu({
	page,
	onPageChange,
	...props
}: SelectorMenuProps & {
	page: MobilePage;
	onPageChange: (page: MobilePage) => void;
}) {
	const selectedTier = props.selectedModel?.serviceTiers.find(
		(tier) => tier.id === props.selectedServiceTier,
	);

	const goTo = (next: Exclude<MobilePage, "root">) => {
		onPageChange(next);
	};

	const goBack = () => {
		onPageChange("root");
	};

	if (page !== "root") {
		const title =
			page === "model" ? "Модель" : page === "effort" ? "Усилие" : "Скорость";
		return (
			<>
				<ModelNavigatorHeader onBack={goBack} pageLabel={title} />
				{page === "model" ? (
					<ModelItems
						models={props.models}
						selectedModelId={props.selectedModelId}
						disabled={props.disabled}
						onModelSelect={props.onModelSelect}
					/>
				) : null}
				{page === "effort" ? (
					<EffortItems
						selectedModel={props.selectedModel}
						selectedEffort={props.selectedEffort}
						disabled={props.disabled}
						onEffortSelect={props.onEffortSelect}
					/>
				) : null}
				{page === "speed" ? (
					<SpeedItems
						selectedModel={props.selectedModel}
						selectedServiceTier={props.selectedServiceTier}
						disabled={props.disabled}
						onServiceTierSelect={props.onServiceTierSelect}
					/>
				) : null}
			</>
		);
	}

	return (
		<>
			<ModelNavigatorRow
				label="Модель"
				value={props.selectedModel?.displayName ?? "Выбрать модель"}
				onNavigate={() => goTo("model")}
			/>
			<DropdownMenuSeparator />
			<DropdownMenuLabel className="text-muted-foreground px-4 pt-2 pb-1 text-[15px] font-semibold">
				Интеллект
			</DropdownMenuLabel>
			{props.selectedModel?.supportedReasoningEfforts.length ? (
				<DropdownMenuRadioGroup value={props.selectedEffort ?? ""}>
					{props.selectedModel.supportedReasoningEfforts.map((effort) => (
						<DropdownMenuRadioItem
							key={effort.id}
							value={effort.id}
							disabled={props.disabled}
							onSelect={(event) => {
								keepMenuOpen(event);
								props.onEffortSelect(effort.id);
							}}
							className="min-h-12 rounded-xl px-4 text-[18px]"
						>
							{EFFORT_NAMES[effort.id] ?? effort.id}
						</DropdownMenuRadioItem>
					))}
				</DropdownMenuRadioGroup>
			) : (
				<p className="text-muted-foreground px-4 py-3 text-sm">
					Для этой модели уровень интеллекта выбирается автоматически.
				</p>
			)}
			<DropdownMenuSeparator />
			<ModelNavigatorRow
				label="Скорость"
				value={serviceTierName(selectedTier)}
				onNavigate={() => goTo("speed")}
				disabled={!props.selectedModel?.serviceTiers.length}
			/>
		</>
	);
}
