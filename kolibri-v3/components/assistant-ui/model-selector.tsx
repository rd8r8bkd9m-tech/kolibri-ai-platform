"use client";

import { useAui } from "@assistant-ui/react";
import { type ReactNode, useEffect } from "react";

export type ModelSelectorEffortOption = {
	id: string;
	name: string;
};

export type ModelOption = {
	id: string;
	name: string;
	description?: string;
	icon?: ReactNode;
	disabled?: boolean;
	keywords?: readonly string[];
	efforts?: boolean | readonly ModelSelectorEffortOption[];
};

export const DEFAULT_EFFORT_OPTIONS: readonly ModelSelectorEffortOption[] = [
	{ id: "low", name: "Low" },
	{ id: "medium", name: "Med" },
	{ id: "high", name: "High" },
];

function modelEfforts(model?: ModelOption) {
	if (!model?.efforts) return undefined;
	return model.efforts === true ? DEFAULT_EFFORT_OPTIONS : model.efforts;
}

export function resolveModelEffort(
	models: readonly ModelOption[],
	modelId: string | undefined,
	effort: string | undefined,
) {
	if (!effort) return undefined;
	const efforts = modelEfforts(models.find((model) => model.id === modelId));
	return efforts?.some((option) => option.id === effort) ? effort : undefined;
}

export type ModelSelectorRootProps = {
	models: readonly ModelOption[];
	value?: string;
	defaultValue?: string;
	effort?: string;
	defaultEffort?: string;
	children: ReactNode;
};

function ModelSelectorRoot({
	models,
	value,
	defaultValue,
	effort,
	defaultEffort,
	children,
}: ModelSelectorRootProps) {
	const api = useAui();
	const modelName = value ?? defaultValue ?? models[0]?.id;
	const reasoningEffort = resolveModelEffort(
		models,
		modelName,
		effort ?? defaultEffort,
	);

	useEffect(() => {
		if (!modelName) return;
		return api.modelContext.register({
			getModelContext: () => ({
				config: {
					modelName,
					...(reasoningEffort ? { reasoningEffort } : {}),
				},
			}),
		});
	}, [api, modelName, reasoningEffort]);

	return children;
}

export const ModelSelector = { Root: ModelSelectorRoot } as const;
export { ModelSelectorRoot };
