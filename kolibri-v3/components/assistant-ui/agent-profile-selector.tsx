"use client";

import { DeveloperModeControl } from "@/components/assistant-ui/developer-mode-control";
import { ModelProfileSelectorControl } from "@/components/assistant-ui/model-profile-selector-control";
import { useIdentity } from "@/lib/identity/provider";
import { type DeveloperAccessMode } from "@/lib/product-chat/developer-agent-mode";

type AgentProfileSelectorProps = {
	surface?: "composer" | "settings" | "mobile-header";
	control?: "model" | "developer";
};

export const AgentProfileSelector = ({
	surface = "composer",
	control = "model",
}: AgentProfileSelectorProps) => {
	const identity = useIdentity();
	if (control === "developer") {
		return <DeveloperModeControl surface={surface} />;
	}

	// Models and providers are platform-admin concerns. Regular users must not
	// see provider names, model ids or connection state anywhere in the UI.
	if (identity.user?.isPlatformOwner !== true) {
		return null;
	}

	return <ModelProfileSelectorControl surface={surface} />;
};

export type { DeveloperAccessMode };
