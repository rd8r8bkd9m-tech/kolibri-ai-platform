"use client";

import { renderGenerativeUI } from "@assistant-ui/react-generative-ui";
import { DashedMutedPanel, PanelContainer } from "@/components/ui/shared-wrappers";
import {
	kolibriGenerativeUILibrary,
	serializeKolibriGenerativeUI,
	KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE,
	KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE,
} from "@/components/assistant-ui/generative-ui-library";
import { sanitizeKolibriGenerativeUI } from "@/lib/generative-ui";
import { uiClassTokens } from "@/components/ui/class-names";

export type KolibriGenerativeUIRendererProps = {
	spec: unknown;
	status?: "streaming" | "done";
	inspectSource?: boolean;
};

export type KolibriGenerativeUIProps = {
	node: unknown;
	status?: "streaming" | "done";
	inspectable?: boolean;
};

export function KolibriGenerativeUI({
	node,
	status = "done",
	inspectable = false,
}: KolibriGenerativeUIProps) {
	return (
		<KolibriGenerativeUIRenderer
			spec={node}
			status={status}
			inspectSource={inspectable}
		/>
	);
}

export function KolibriGenerativeUIRenderer({
	spec,
	status = "done",
	inspectSource = false,
}: KolibriGenerativeUIRendererProps) {
	const validation = sanitizeKolibriGenerativeUI(spec);

	if (!validation.ok) {
		return (
			<DashedMutedPanel
				role="status"
				aria-live="polite"
				data-slot="kolibri-generative-ui-fallback"
			>
				{status === "streaming"
					? KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE
					: KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE}
			</DashedMutedPanel>
		);
	}

	const source = inspectSource
		? serializeKolibriGenerativeUI(validation.value)
		: "";
	const rootType =
		typeof validation.value === "object" &&
		validation.value !== null &&
		!Array.isArray(validation.value) &&
		"$type" in validation.value &&
		typeof validation.value.$type === "string"
			? validation.value.$type
			: null;
	const isProductWidget =
		rootType === "WeatherWidget" ||
		rootType === "EstimateGenerationActivity" ||
		rootType === "EstimateEditor" ||
		rootType === "EstimateDocumentPack";
	const renderedNode = renderGenerativeUI(
		validation.value,
		kolibriGenerativeUILibrary,
		{ status },
	);

	if (isProductWidget) {
		return (
			<div
				className={uiClassTokens.generativeUiContainerMinWidth}
				data-slot="kolibri-product-widget"
				data-generative-ui-status={status}
			>
				{renderedNode}
			</div>
		);
	}

	return (
			<PanelContainer
				data-slot="kolibri-generative-ui"
				data-generative-ui-status={status}
				aria-label="Сгенерированное представление Kolibri"
			>
				<p
					className={uiClassTokens.generativeProvenanceNote}
					data-slot="kolibri-generative-ui-provenance"
				>
					Представление ИИ · не является подтверждением
				</p>
			{renderedNode}

			{inspectSource ? (
				<details className={uiClassTokens.generativeDetailsTrigger}>
					<summary className={uiClassTokens.generativeSummary}>
						Структура блока
					</summary>
					<pre
						className={uiClassTokens.generativeSource}
						aria-label="Безопасное описание сгенерированного интерфейса"
						tabIndex={0}
					>
						<code>{source}</code>
					</pre>
				</details>
			) : null}
		</PanelContainer>
	);
}
