"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import type { MouseEvent } from "react";
import { useRef } from "react";
import type { SelectorMenuProps } from "@/components/assistant-ui/model-selector-controls";
import {
	catalogModelSelectionId,
	compactModelName,
	EFFORT_NAMES,
	mobileEffortDescription,
	serviceTierName,
} from "@/components/assistant-ui/model-selector-utils";
import { Button } from "@/components/ui/button";
import {
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";

export function keepMenuOpen(event: Event) {
	event.preventDefault();
}

export function compactModelOptionName(name: string) {
	return compactModelName(name);
}

export function ModelItems({
	models,
	selectedModelId,
	disabled,
	onModelSelect,
}: Pick<
	SelectorMenuProps,
	"models" | "selectedModelId" | "disabled" | "onModelSelect"
>) {
	return (
		<DropdownMenuRadioGroup value={selectedModelId ?? ""}>
			{models.map((model) => {
				const selectionId = catalogModelSelectionId(model);
				return (
				<DropdownMenuRadioItem
					key={selectionId}
					value={selectionId}
					disabled={disabled || !model.available}
					onSelect={(event) => {
						keepMenuOpen(event);
						onModelSelect(selectionId);
					}}
					className="min-h-11 gap-3 px-3 py-2 text-[15px]"
				>
					<span className="min-w-0 flex-1 truncate">
						{compactModelOptionName(model.displayName)}
					</span>
					{!model.available ? (
						<span className="text-muted-foreground shrink-0 text-xs">
							Не подключено
						</span>
					) : null}
				</DropdownMenuRadioItem>
				);
			})}
		</DropdownMenuRadioGroup>
	);
}

export function EffortItems({
	selectedModel,
	selectedEffort,
	disabled,
	onEffortSelect,
}: Pick<
	SelectorMenuProps,
	"selectedModel" | "selectedEffort" | "disabled" | "onEffortSelect"
>) {
	const efforts = selectedModel?.supportedReasoningEfforts ?? [];
	return (
		<>
			<DropdownMenuLabel className="text-muted-foreground px-3 pt-2 pb-1 text-sm font-normal">
				Усилия
			</DropdownMenuLabel>
			{efforts.length > 0 ? (
				<DropdownMenuRadioGroup value={selectedEffort ?? ""}>
					{efforts.map((effort) => (
						<DropdownMenuRadioItem
							key={effort.id}
							value={effort.id}
							disabled={disabled}
							onSelect={(event) => {
								keepMenuOpen(event);
								onEffortSelect(effort.id);
							}}
							className="min-h-11 items-start px-3 py-2 text-[15px]"
						>
							<span className="min-w-0 flex-1">
								<span className="block">
									{EFFORT_NAMES[effort.id] ?? effort.id}
								</span>
								{effort.id === "ultra" ? (
									<span className="text-muted-foreground mt-0.5 block text-xs leading-4">
										{mobileEffortDescription(effort.id)}
									</span>
								) : null}
							</span>
						</DropdownMenuRadioItem>
					))}
				</DropdownMenuRadioGroup>
			) : (
				<p className="text-muted-foreground px-3 py-3 text-sm">
					Эта модель не поддерживает выбор усилия.
				</p>
			)}
		</>
	);
}

export function SpeedItems({
	selectedModel,
	selectedServiceTier,
	disabled,
	onServiceTierSelect,
}: Pick<
	SelectorMenuProps,
	"selectedModel" | "selectedServiceTier" | "disabled" | "onServiceTierSelect"
>) {
	const tiers = selectedModel?.serviceTiers ?? [];
	const value = selectedServiceTier ?? "standard";
	return (
		<>
			<DropdownMenuLabel className="text-muted-foreground px-3 pt-2 pb-1 text-sm font-normal">
				Скорость
			</DropdownMenuLabel>
			<DropdownMenuRadioGroup value={value}>
				<DropdownMenuRadioItem
					value="standard"
					disabled={disabled}
					onSelect={(event) => {
						keepMenuOpen(event);
						onServiceTierSelect(null);
					}}
					className="min-h-14 items-start px-3 py-2 text-[15px]"
				>
					<span className="min-w-0 flex-1">
						<span className="block">Стандартный</span>
						<span className="text-muted-foreground mt-0.5 block text-xs">
							Стандартная скорость
						</span>
					</span>
				</DropdownMenuRadioItem>
				{tiers.map((tier) => (
					<DropdownMenuRadioItem
						key={tier.id}
						value={tier.id}
						disabled={disabled}
						onSelect={(event) => {
							keepMenuOpen(event);
							onServiceTierSelect(tier.id);
						}}
						className="min-h-14 items-start px-3 py-2 text-[15px]"
					>
						<span className="min-w-0 flex-1">
							<span className="block">{serviceTierName(tier)}</span>
							<span className="text-muted-foreground mt-0.5 block text-xs leading-4">
								{tier.id === "priority"
									? "Скорость 1,5×, больше использования"
									: tier.description}
							</span>
						</span>
					</DropdownMenuRadioItem>
				))}
			</DropdownMenuRadioGroup>
		</>
	);
}

export function ModelNavigatorHeader({
	onBack,
	pageLabel,
}: {
	onBack: () => void;
	pageLabel: string;
}) {
	const backRef = useRef<HTMLButtonElement>(null);

	const onBackClick = (event: MouseEvent<HTMLButtonElement>) => {
		event.preventDefault();
		event.stopPropagation();
		onBack();
		window.requestAnimationFrame(() => backRef.current?.focus());
	};

	return (
		<div className="flex min-h-12 items-center border-b px-1">
			<Button
				ref={backRef}
				type="button"
				variant="ghost"
				size="sm"
				onPointerDown={(event) => event.stopPropagation()}
				onClick={onBackClick}
				className="min-h-11 rounded-xl px-2"
			>
				<ChevronLeftIcon className="size-4" aria-hidden="true" />
				Назад
			</Button>
			<span className="pr-3 text-sm font-medium">{pageLabel}</span>
		</div>
	);
}

export function ModelNavigatorRow({
	label,
	value,
	onNavigate,
	disabled = false,
	icon = true,
}: {
	label: string;
	value: string;
	onNavigate: () => void;
	disabled?: boolean;
	icon?: boolean;
}) {
	return (
		<DropdownMenuItem
			onSelect={(event) => {
				keepMenuOpen(event);
				onNavigate();
			}}
			disabled={disabled}
			className="min-h-11 rounded-2xl px-4 text-[18px]"
		>
			<span className="min-w-0 flex-1 truncate">{label}</span>
			<span className="text-muted-foreground ml-auto max-w-28 truncate">
				{value}
			</span>
			{icon ? <ChevronRightIcon className="size-4" aria-hidden="true" /> : null}
		</DropdownMenuItem>
	);
}
