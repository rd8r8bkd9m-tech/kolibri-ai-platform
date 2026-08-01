"use client";

import type {
	ModelOption,
	ModelSelectorEffortOption,
} from "@/components/assistant-ui/model-selector";
import type { CatalogModel, ServiceTierOption } from "@/lib/models/client";
import {
	catalogModelSelectionId,
	effectiveModelSelectionId,
} from "@/lib/models/selection";

export { catalogModelSelectionId } from "@/lib/models/selection";

export const MOBILE_SELECTOR_QUERY = "(max-width: 959px)";

export const EFFORT_NAMES: Readonly<Record<string, string>> = {
	low: "Лёгкий",
	medium: "Средний",
	high: "Высокий",
	xhigh: "Очень высокий",
	max: "Макс.",
	ultra: "Ультра",
};

const EFFORT_DESCRIPTIONS: Readonly<Record<string, string>> = {
	low: "Быстрые ответы для простых задач",
	medium: "Баланс скорости и качества",
	high: "Больше времени на сложную задачу",
	xhigh: "Глубокий анализ и проверка решения",
	max: "Максимальная глубина рассуждений",
	ultra: "Быстрее расходует лимит использования",
};

export function subscribeMobileSelector(listener: () => void) {
	const media = window.matchMedia(MOBILE_SELECTOR_QUERY);
	media.addEventListener("change", listener);
	return () => media.removeEventListener("change", listener);
}

export function mobileSelectorSnapshot() {
	return window.matchMedia(MOBILE_SELECTOR_QUERY).matches;
}

export function serverMobileSelectorSnapshot() {
	return false;
}

export function compactModelName(name: string) {
	return name.replace(/^GPT-/i, "");
}

export function effortOptions(
	model: CatalogModel,
): readonly ModelSelectorEffortOption[] | undefined {
	if (model.supportedReasoningEfforts.length === 0) return undefined;
	return model.supportedReasoningEfforts.map((effort) => ({
		id: effort.id,
		name: EFFORT_NAMES[effort.id] ?? effort.id,
	}));
}

export function toModelOption(model: CatalogModel): ModelOption {
	return {
		id: catalogModelSelectionId(model),
		name: compactModelName(model.displayName),
		description: model.available
			? model.description
			: `${model.description} Сначала подключите провайдера.`,
		disabled: !model.available,
		keywords: [
			model.profile,
			model.id,
			model.displayName,
		],
		efforts: effortOptions(model),
	};
}

export function effectiveModelId(
	models: readonly CatalogModel[],
	user: {
		preferredAgentProfile?: string | null;
		preferredModel?: string | null;
	} | null,
) {
	return effectiveModelSelectionId(models, user);
}

export function serviceTierName(tier: ServiceTierOption | undefined) {
	if (!tier) return "Стандартный";
	if (tier.id === "priority") return "Быстрый";
	return tier.name;
}

export function mobileEffortDescription(effortId: string) {
	return EFFORT_DESCRIPTIONS[effortId];
}
