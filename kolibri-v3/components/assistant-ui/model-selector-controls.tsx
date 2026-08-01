"use client";

import { DesktopSelectorMenu } from "@/components/assistant-ui/model-selector-desktop-menu";
import {
	EffortItems,
	ModelItems,
	SpeedItems,
} from "@/components/assistant-ui/model-selector-items";
import { MobileSelectorMenu } from "@/components/assistant-ui/model-selector-mobile-menu";
import type { CatalogModel } from "@/lib/models/client";

export type MobilePage = "root" | "model" | "effort" | "speed";

export type SelectorMenuProps = {
	models: readonly CatalogModel[];
	selectedModelId: string | undefined;
	selectedModel: CatalogModel | undefined;
	selectedEffort: string | undefined;
	selectedServiceTier: string | null;
	disabled: boolean;
	saving: boolean;
	onModelSelect: (id: string) => void;
	onEffortSelect: (id: string) => void;
	onServiceTierSelect: (id: string | null) => void;
};

export {
	DesktopSelectorMenu,
	EffortItems,
	MobileSelectorMenu,
	ModelItems,
	SpeedItems,
};
