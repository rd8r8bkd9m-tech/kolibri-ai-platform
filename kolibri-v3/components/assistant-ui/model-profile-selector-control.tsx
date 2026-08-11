"use client";

import { useAuiState } from "@assistant-ui/react";
import { ChevronDownIcon, LoaderCircleIcon, ZapIcon } from "lucide-react";
import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ModelSelector } from "@/components/assistant-ui/model-selector";
import {
	DesktopSelectorMenu,
	type MobilePage,
	MobileSelectorMenu,
	type SelectorMenuProps,
} from "@/components/assistant-ui/model-selector-controls";
import {
	catalogModelSelectionId,
	compactModelName,
	EFFORT_NAMES,
	effectiveModelId,
	mobileSelectorSnapshot,
	serverMobileSelectorSnapshot,
	serviceTierName,
	subscribeMobileSelector,
	toModelOption,
} from "@/components/assistant-ui/model-selector-utils";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useIdentity } from "@/lib/identity/provider";
import { useModelCatalog } from "@/lib/models/provider";

type ModelProfileSelectorProps = {
	surface?: "composer" | "settings" | "mobile-header";
};

export function ModelProfileSelectorControl({
	surface = "composer",
}: ModelProfileSelectorProps) {
	const identity = useIdentity();
	const modelCatalog = useModelCatalog();
	const isRunning = useAuiState((state) => state.thread.isRunning);
	const [open, setOpen] = useState(false);
	const [mobilePage, setMobilePage] = useState<MobilePage>("root");
	const mobilePageRef = useRef<MobilePage>("root");
	const [error, setError] = useState<string | null>(null);
	const retryRef = useRef<(() => Promise<void>) | null>(null);
	const selectionInFlightRef = useRef(false);

	const isMobileSelector = useSyncExternalStore(
		subscribeMobileSelector,
		mobileSelectorSnapshot,
		serverMobileSelectorSnapshot,
	);

	const catalogModels = useMemo(() => {
		const models = modelCatalog.catalog?.models ?? [];
		const preferred = identity.user?.preferredModel;
		const preferredProfile = identity.user?.preferredAgentProfile;
		if (
			preferred &&
			preferredProfile &&
			!models.some(
				(model) =>
					model.profile === preferredProfile && model.id === preferred,
			)
		) {
			return [
				...models,
				{
					id: preferred,
					profile: preferredProfile,
					displayName: preferred,
					description: "Сохранённая модель временно недоступна.",
					available: false,
					supportedReasoningEfforts: [],
					serviceTiers: [],
					defaultReasoningEffort: null,
					isDefault: false,
					selectionSupported: false,
					upgrade: null,
				},
			];
		}
		return models;
	}, [
		identity.user?.preferredAgentProfile,
		identity.user?.preferredModel,
		modelCatalog.catalog?.models,
	]);

	const modelOptions = useMemo(
		() => catalogModels.map(toModelOption),
		[catalogModels],
	);

	if (identity.status !== "authenticated" || !identity.user) return null;

	const selectedModelId = effectiveModelId(
		catalogModels,
		{
			preferredAgentProfile: identity.user.preferredAgentProfile,
			preferredModel: identity.user.preferredModel,
		},
	);
	const selectedModel = catalogModels.find(
		(model) => catalogModelSelectionId(model) === selectedModelId,
	);
	const preferredEffort = identity.user.preferredReasoningEffort;
	const selectedEffort = selectedModel?.supportedReasoningEfforts.some(
		(effort) => effort.id === preferredEffort,
	)
		? (preferredEffort ?? undefined)
		: (selectedModel?.defaultReasoningEffort ?? undefined);
	const preferredServiceTier = identity.user.preferredServiceTier;
	const selectedServiceTier = selectedModel?.serviceTiers.some(
		(tier) => tier.id === preferredServiceTier,
	)
		? preferredServiceTier
		: null;
	const selectedTier = selectedModel?.serviceTiers.find(
		(tier) => tier.id === selectedServiceTier,
	);
	const saving = identity.modelSettingsSaving || identity.agentProfileSaving;
	const disabled = saving || isRunning;

	const modelName = selectedModel
		? compactModelName(selectedModel.displayName)
		: "Модель";
	const effortName = selectedEffort
		? (EFFORT_NAMES[selectedEffort] ?? selectedEffort)
		: null;
	const speedName = serviceTierName(selectedTier);
	const triggerAccessibleLabel = [
		`Модель: ${modelName}`,
		effortName ? `Усилие: ${effortName}` : null,
		selectedModel?.serviceTiers.length ? `Скорость: ${speedName}` : null,
		"Открыть выбор",
	]
		.filter(Boolean)
		.join(". ");

	const runSelection = async (
		action: () => Promise<void>,
		fallbackMessage: string,
	) => {
		if (selectionInFlightRef.current) return;
		selectionInFlightRef.current = true;
		setError(null);
		try {
			await action();
			retryRef.current = null;
		} catch (requestError) {
			setError(
				requestError instanceof Error && requestError.message.trim()
					? requestError.message
					: fallbackMessage,
			);
			retryRef.current = () => runSelection(action, fallbackMessage);
		} finally {
			selectionInFlightRef.current = false;
		}
	};

	const selectModel = async (value: string) => {
		if (isMobileSelector && mobilePageRef.current !== "model") {
			return;
		}
		const model = catalogModels.find(
			(candidate) => catalogModelSelectionId(candidate) === value,
		);
		if (!model?.available || disabled) return;
		const currentEffort = identity.user?.preferredReasoningEffort;
		const nextEffort = model.supportedReasoningEfforts.some(
			(candidate) => candidate.id === currentEffort,
		)
			? (currentEffort ?? model.defaultReasoningEffort)
			: model.defaultReasoningEffort;
		const currentTier = identity.user?.preferredServiceTier;
		const nextServiceTier =
			currentTier &&
			model.serviceTiers.some((tier) => tier.id === currentTier)
				? currentTier
				: null;
		if (
			model.profile === identity.user?.preferredAgentProfile &&
			model.id === identity.user.preferredModel &&
			nextEffort === identity.user?.preferredReasoningEffort &&
			nextServiceTier === identity.user?.preferredServiceTier
		) {
			return;
		}
		await runSelection(
			() =>
				identity.setModelSettings({
					profile: model.profile,
					model: model.id === "auto" ? null : model.id,
					reasoningEffort: nextEffort,
					serviceTier: nextServiceTier,
				}),
			"Не удалось сменить модель.",
		);
	};

	const selectEffort = async (effort: string) => {
		if (
			disabled ||
			(isMobileSelector && mobilePageRef.current !== "effort") ||
			!selectedModel ||
			!selectedModel.supportedReasoningEfforts.some(
				(candidate) => candidate.id === effort,
			) ||
			effort === identity.user?.preferredReasoningEffort
		) {
			return;
		}
		await runSelection(
			() =>
				identity.setModelSettings({
					profile: selectedModel.profile,
					model: selectedModel.id,
					reasoningEffort: effort,
					serviceTier: selectedServiceTier,
				}),
			"Не удалось изменить усилие.",
		);
	};

	const selectServiceTier = async (serviceTier: string | null) => {
		if (
			disabled ||
			(isMobileSelector && mobilePageRef.current !== "speed") ||
			!selectedModel ||
			(serviceTier !== null &&
				!selectedModel.serviceTiers.some(
					(candidate) => candidate.id === serviceTier,
				)) ||
			serviceTier === identity.user?.preferredServiceTier
		) {
			return;
		}
		await runSelection(
			() =>
				identity.setModelSettings({
					profile: selectedModel.profile,
					model: selectedModel.id,
					reasoningEffort: selectedEffort ?? null,
					serviceTier,
				}),
			"Не удалось изменить скорость.",
		);
	};

	const menuProps: SelectorMenuProps = {
		models: catalogModels,
		selectedModelId,
		selectedModel,
		selectedEffort,
		selectedServiceTier,
		disabled,
		saving,
		onModelSelect: (id) => void selectModel(id),
		onEffortSelect: (id) => void selectEffort(id),
		onServiceTierSelect: (id) => void selectServiceTier(id),
	};

	return (
		<div
			className={
				surface === "settings"
					? "relative w-full"
					: surface === "mobile-header"
						? "relative"
						: "relative min-w-0"
			}
		>
			<ModelSelector.Root
				models={modelOptions}
				value={selectedModelId}
				effort={selectedEffort}
			>
				<DropdownMenu
					open={open}
					onOpenChange={(nextOpen) => {
						setOpen(nextOpen);
						if (nextOpen) {
							mobilePageRef.current = "root";
							setMobilePage("root");
						}
					}}
				>
					<DropdownMenuTrigger asChild>
						<Button
							type="button"
							variant={surface === "settings" ? "outline" : "ghost"}
							disabled={isRunning}
							aria-busy={saving}
							aria-label={triggerAccessibleLabel}
							aria-describedby={error ? "model-selector-error" : undefined}
							className={
								surface === "settings"
									? "h-11 w-full justify-between rounded-xl px-3"
									: surface === "mobile-header"
										? "h-11 gap-1 rounded-xl px-3 text-[21px] leading-none font-semibold tracking-[-0.035em] underline decoration-[1.5px] underline-offset-4"
										: "h-11 max-w-[9rem] min-w-0 gap-1.5 rounded-full px-2 text-xs min-[960px]:h-9 min-[960px]:max-w-56 min-[960px]:px-3 min-[960px]:text-sm"
							}
						>
							{surface === "mobile-header" ? (
								<>
									<span>Chat</span>
									<ChevronDownIcon
										className="text-muted-foreground size-5 shrink-0"
										aria-hidden="true"
									/>
								</>
							) : (
								<>
									{saving ? (
										<LoaderCircleIcon
											className="size-3.5 shrink-0 animate-spin"
											aria-hidden="true"
										/>
									) : (
										<ZapIcon
											className="size-3.5 shrink-0 fill-current"
											aria-hidden="true"
										/>
									)}
									<span className="min-w-0 truncate">{modelName}</span>
									{effortName ? (
										<span className="text-muted-foreground hidden min-w-0 truncate min-[960px]:inline">
											{effortName}
										</span>
									) : null}
									<ChevronDownIcon
										className="text-muted-foreground size-3.5 shrink-0"
										aria-hidden="true"
									/>
								</>
							)}
						</Button>
					</DropdownMenuTrigger>
					<DropdownMenuContent
						align={
							surface === "settings"
								? "start"
								: surface === "mobile-header"
									? "center"
									: isMobileSelector
										? "start"
										: "end"
						}
						alignOffset={isMobileSelector && surface === "composer" ? 56 : 0}
						sideOffset={8}
						onEscapeKeyDown={(event) => {
							if (isMobileSelector && mobilePage !== "root") {
								event.preventDefault();
								setMobilePage("root");
							}
						}}
						onKeyDown={(event) => {
							if (
								isMobileSelector &&
								mobilePage !== "root" &&
								event.key === "ArrowLeft"
							) {
								event.preventDefault();
								setMobilePage("root");
							}
						}}
						className={
							surface === "mobile-header"
								? "z-[80] w-[min(24rem,calc(100vw-1.5rem))] rounded-[2rem] border-foreground/45 p-3 shadow-xl"
								: isMobileSelector
									? "z-[80] w-[min(15.5rem,calc(100vw-1.5rem))] rounded-[1.75rem] border-foreground/35 p-2 shadow-xl"
									: "z-[80] w-[min(20rem,calc(100vw-1rem))] rounded-2xl p-1.5 shadow-xl"
						}
					>
						{isMobileSelector ? (
							<MobileSelectorMenu
								{...menuProps}
								page={mobilePage}
								onPageChange={(page) => {
									mobilePageRef.current = page;
									setMobilePage(page);
								}}
							/>
						) : (
							<DesktopSelectorMenu {...menuProps} />
						)}
					</DropdownMenuContent>
				</DropdownMenu>
			</ModelSelector.Root>

			{error ? (
				<div
					id="model-selector-error"
					role="alert"
					className="border-destructive/25 bg-popover text-destructive absolute right-0 bottom-full z-[100] mb-2 flex w-72 items-center gap-2 rounded-xl border px-3 py-2 text-xs leading-relaxed shadow-lg"
				>
					<span className="min-w-0 flex-1">{error}</span>
					<Button
						type="button"
						variant="ghost"
						size="sm"
						className="h-7 shrink-0 px-2 text-xs"
						onClick={() => void retryRef.current?.()}
					>
						Повторить
					</Button>
				</div>
			) : null}
		</div>
	);
}
