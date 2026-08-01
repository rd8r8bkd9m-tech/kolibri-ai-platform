"use client";

import {
	KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE,
	KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE,
} from "./styles";
import { uiClassTokens } from "@/components/ui/class-names";
import { DashedMutedPanel } from "@/components/ui/shared-wrappers";

export function QuietGenerativeUIFallback({
	streaming = false,
}: {
	streaming?: boolean;
}) {
	return (
		<DashedMutedPanel
			role="status"
			aria-live="polite"
		>
			{streaming
				? KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE
				: KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE}
		</DashedMutedPanel>
	);
}

export function Heading({
	heading,
	level = 3,
}: {
	heading: string;
	level?: 2 | 3 | 4;
}) {
	const className =
		level === 2
			? uiClassTokens.presentationHeading2
			: level === 3
				? uiClassTokens.presentationHeading3
				: uiClassTokens.presentationHeading4;

	if (level === 2) return <h2 className={className}>{heading}</h2>;
	if (level === 4) return <h4 className={className}>{heading}</h4>;
	return <h3 className={className}>{heading}</h3>;
}
