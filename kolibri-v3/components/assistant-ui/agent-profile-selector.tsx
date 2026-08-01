"use client";

import { DeveloperModeControl } from "@/components/assistant-ui/developer-mode-control";
import { ModelProfileSelectorControl } from "@/components/assistant-ui/model-profile-selector-control";
import { type DeveloperAccessMode } from "@/lib/product-chat/developer-agent-mode";

type AgentProfileSelectorProps = {
	surface?: "composer" | "settings" | "mobile-header";
	control?: "model" | "developer";
};

export const AgentProfileSelector = ({
	surface = "composer",
	control = "model",
}: AgentProfileSelectorProps) => {
	if (control === "developer") {
		return <DeveloperModeControl surface={surface} />;
	}

	return <ModelProfileSelectorControl surface={surface} />;
};

export type { DeveloperAccessMode };
