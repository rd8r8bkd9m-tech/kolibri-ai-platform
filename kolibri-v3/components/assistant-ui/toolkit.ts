"use client";

import { defineToolkit } from "@assistant-ui/react";

import { DeveloperCommandToolUI, DeveloperFileChangeToolUI } from "./developer-activity-tool";
import { GeneratedImageToolUI } from "./generated-image-tool";
import { kolibriPresentParameters, kolibriPresentTool } from "./generative-ui-library";
import { WeatherToolUI } from "./product-widgets/weather";

/**
 * The single assistant-ui tool registry for the product UI.
 *
 * These are backend tools: execution remains in the AG-UI product runtime.
 * Keeping only declarations and renderers here means the registry cannot
 * accidentally bypass tenant-aware server authorization or persistence.
 */
export const kolibriToolkit = defineToolkit({
	generate_image: {
		description:
			"Создать изображение и вернуть проверенный same-origin attachment.",
		parameters: {
				type: "object",
				additionalProperties: false,
				properties: {
					prompt: { type: "string", minLength: 1, maxLength: 8_000 },
				},
				required: ["prompt"],
		} as const,
		render: GeneratedImageToolUI,
	},
	get_weather: {
		description:
			"Получить текущую погоду и прогноз для однозначно определённого населённого пункта.",
		parameters: {
			type: "object",
			additionalProperties: false,
			properties: {
				location: { type: "string", minLength: 1, maxLength: 160 },
				forecastDays: { type: "integer", minimum: 1, maximum: 7 },
			},
			required: ["location", "forecastDays"],
		} as const,
		render: WeatherToolUI,
	},
	developer_command: {
		description: "Выполнить разрешённую команду developer-агента.",
		parameters: {
			type: "object",
			additionalProperties: false,
			properties: {
				command: { type: "string", minLength: 1, maxLength: 4_000 },
				cwd: { type: "string", maxLength: 1_024 },
			},
			required: ["command"],
		} as const,
		render: DeveloperCommandToolUI,
	},
	developer_file_change: {
		description: "Показать изменения файлов, выполненные developer-агентом.",
		parameters: {
			type: "object",
			additionalProperties: false,
			properties: {
				files: {
					type: "array",
					maxItems: 40,
					items: {
						type: "object",
						additionalProperties: false,
						properties: {
							path: { type: "string", maxLength: 1_024 },
							diff: { type: "string", maxLength: 100_000 },
						},
						required: ["path"],
					},
				},
			},
			required: ["files"],
		} as const,
		render: DeveloperFileChangeToolUI,
	},
	present: {
		description: kolibriPresentTool.description,
		parameters: kolibriPresentParameters,
		render: kolibriPresentTool.render,
	},
});
