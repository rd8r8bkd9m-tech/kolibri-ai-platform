import { z } from "zod";

export const KOLIBRI_GENERATIVE_UI_LIMITS = {
	maxDepth: 8,
	maxNodes: 96,
	maxChildrenPerNode: 200,
	maxObjectEntries: 24,
	maxTextLength: 2_000,
	maxTotalTextLength: 12_000,
	maxPropStringLength: 600,
	maxKeyLength: 64,
	maxStableKeyLength: 96,
} as const;

const shortText = z
	.string()
	.trim()
	.min(1)
	.max(KOLIBRI_GENERATIVE_UI_LIMITS.maxPropStringLength);

const longText = z
	.string()
	.trim()
	.min(1)
	.max(KOLIBRI_GENERATIVE_UI_LIMITS.maxTextLength);

const optionalPlaceText = z.string().trim().max(160).optional();

const forecastDay = z
	.object({
		date: z.string().trim().min(1).max(32),
		condition: z.string().trim().min(1).max(160).optional(),
		weatherCode: z.number().int().min(0).max(99).optional(),
		temperatureMax: z.number().finite().min(-100).max(100).optional(),
		temperatureMin: z.number().finite().min(-100).max(100).optional(),
		precipitationProbability: z.number().int().min(0).max(100).optional(),
	})
	.strict();

const weatherSource = z
	.object({
		label: z.string().trim().min(1).max(160),
		sourceUrl: z.string().trim().url().max(1_000).nullable().optional(),
	})
	.strict();

const estimateRow = z
	.object({
		id: z.string().regex(/^row_[A-Za-z0-9._~-]{8,96}$/),
		section: z.string().trim().min(1).max(120).default("Прочее"),
		kind: z
			.enum([
				"work",
				"material",
				"equipment",
				"service",
				"overhead",
				"tax",
				"contingency",
			])
			.default("service"),
		description: z.string().trim().min(1).max(300),
		unit: z.string().trim().min(1).max(32),
		quantity: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/),
		unitPrice: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/),
		lineTotal: z.string().regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
		quantityBasis: z.string().trim().min(1).max(500).default("Введено вручную"),
		priceBasis: z.string().trim().min(1).max(500).default("Введено вручную"),
		catalogEntryId: z.string().trim().min(1).max(160).optional(),
		catalogEntryVersion: z.number().int().min(1).optional(),
		technologyCardVersion: z.string().trim().min(1).max(160).optional(),
		operationId: z.string().trim().min(1).max(160).optional(),
		resourceId: z.string().trim().min(1).max(160).optional(),
		evidenceId: z.string().trim().min(1).max(160).optional(),
		wbsPath: z.string().trim().min(1).max(500).optional(),
		specification: z.string().trim().min(1).max(500).optional(),
		quantityFormula: z.string().trim().min(1).max(500).optional(),
		priceObservationId: z.string().trim().min(1).max(160).optional(),
		marketAggregateId: z.string().trim().min(1).max(160).optional(),
		lineConfidence: z
			.enum(["missing", "preliminary", "source_backed", "verified"])
			.default("missing"),
		priceEvidence: z
			.object({
				status: z.enum(["current", "stale"]),
				sourceType: z.enum(["fgis_cs", "supplier_offer"]),
				sourceLabel: z.string().trim().min(1).max(240),
				sourceUrl: z.string().trim().url().max(1_000),
				sourceReference: z.string().trim().min(1).max(300),
				snapshotHash: z.string().regex(/^sha256:[0-9a-f]{64}$/),
				quoteId: z.string().regex(/^price_quote_[A-Za-z0-9._~-]{8,96}$/),
				materialCode: z.string().trim().min(1).max(160).nullable(),
				materialName: z.string().trim().min(1).max(500).nullable(),
				region: z.string().trim().min(1).max(240),
				priceZone: z.string().trim().min(1).max(240).nullable(),
				period: z.string().trim().min(1).max(160).nullable(),
				priceDate: z.string().trim().min(10).max(64),
				retrievedAt: z.string().trim().min(10).max(64),
				freshUntil: z.string().trim().min(10).max(64),
				freshnessBasis: z.enum([
					"kolibri_policy_window",
					"supplier_valid_until",
				]),
				taxStatus: z.enum(["excluded", "included", "unknown"]),
				priceScope: z.enum(["official_reference", "landed"]),
				unitPrice: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
				deliveryPerUnit: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
				landedUnitPrice: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
				landedCostStatus: z.enum(["not_calculated", "calculated"]),
				sourceDistancePrice: z
					.string()
					.regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/)
					.nullable(),
				sourceProcurementStoragePercent: z
					.string()
					.trim()
					.min(1)
					.max(64)
					.nullable(),
				bindingStatus: z.enum([
					"indicative",
					"user_attested_indicative",
					"user_attested_binding",
				]),
				availability: z.enum(["available", "unknown", "unavailable"]),
				leadTimeDays: z.number().int().min(0).max(3650).nullable(),
			})
			.strict()
			.nullable()
			.default(null),
		enginePriceProvenance: z
			.object({
				sourceId: z.string().trim().min(1).max(300),
				sourceType: z.enum([
					"regional_catalog",
					"supplier_offer",
					"organization_price",
					"user_price",
					"ai_candidate",
				]),
				label: z.string().trim().min(1).max(300),
				reference: z.string().trim().min(1).max(300),
				sourceUrl: z
					.string()
					.trim()
					.max(2_048)
					.refine(
						(value) =>
							value.startsWith("https://") || value.startsWith("document://"),
					),
				region: z.string().trim().min(1).max(160),
				observedAt: z.string().trim().min(10).max(64),
				validUntil: z.string().trim().min(10).max(32).nullable(),
				verified: z.boolean(),
				itemCode: z.string().trim().min(1).max(120),
				unitPrice: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
				currency: z.literal("RUB"),
				vatMode: z.enum(["included", "excluded", "not_applicable", "unknown"]),
				confidence: z.string().regex(/^(?:0(?:\.\d{1,6})?|1(?:\.0{1,6})?)$/),
			})
			.strict()
			.optional(),
	})
	.strict();

const estimateDocumentPreview = z
	.object({
		title: z.string().trim().min(1).max(240),
		objectName: z.string().trim().min(1).max(240),
		region: z.string().trim().min(1).max(160),
		date: z.string().trim().max(32),
		validUntil: z.string().trim().max(32),
		number: z.string().trim().min(1).max(64),
		status: z.enum(["preliminary", "issued"]),
		mode: z.enum(["preliminary", "issue"]),
		customerName: z.string().trim().max(240).nullable(),
		contractorName: z.string().trim().max(240).nullable(),
		sections: z
			.array(
				z.object({
					name: z.string().trim().min(1).max(160),
					total: z.string().trim().max(40),
				})
				.strict(),
			)
			.max(50),
		lines: z
			.array(
				z.object({
					position: z.number().int().min(1).max(1_000_000),
					section: z.string().trim().min(1).max(160),
					description: z.string().trim().min(1).max(300),
					unit: z.string().trim().min(1).max(40),
					quantity: z.string().trim().max(40),
					unitPrice: z.string().trim().max(40),
					lineTotal: z.string().trim().max(40),
					confidence: z.string().trim().max(40),
				})
				.strict(),
			)
			.max(200),
		totalLines: z.number().int().min(0).max(1_000_000),
		truncated: z.boolean(),
		directTotal: z.string().trim().max(40),
		reserve: z.string().trim().max(40),
		tax: z.string().trim().max(40),
		total: z.string().trim().max(40),
		totalWords: z.string().trim().max(300),
		taxMode: z.string().trim().max(120),
		conditions: z.array(z.string().trim().min(1).max(500)).max(20),
		exclusions: z.array(z.string().trim().min(1).max(500)).max(20),
		paymentSchedule: z
			.array(
				z.object({
					label: z.string().trim().min(1).max(240),
					percent: z.string().trim().max(40),
				})
				.strict(),
			)
			.max(20),
	})
	.strict();

export const kolibriGenerativeUIComponentSchemas = {
	Card: z
		.object({
			title: shortText.optional(),
			description: longText.optional(),
			cardTone: z.enum(["neutral", "subtle", "positive", "warning"]).optional(),
		})
		.strict(),
	Stack: z
		.object({
			gap: z.enum(["compact", "regular", "relaxed"]).optional(),
			align: z.enum(["start", "center", "stretch"]).optional(),
		})
		.strict(),
	Grid: z
		.object({
			columns: z.union([z.literal(1), z.literal(2), z.literal(3)]).optional(),
			gridGap: z.enum(["compact", "regular", "relaxed"]).optional(),
		})
		.strict(),
	Heading: z
		.object({
			heading: shortText,
			level: z.union([z.literal(2), z.literal(3), z.literal(4)]).optional(),
		})
		.strict(),
	Text: z
		.object({
			text: longText,
			textTone: z.enum(["default", "muted", "positive", "warning"]).optional(),
			textSize: z.enum(["small", "regular", "large"]).optional(),
		})
		.strict(),
	Badge: z
		.object({
			label: shortText,
			badgeTone: z
				.enum(["neutral", "positive", "warning", "critical"])
				.optional(),
		})
		.strict(),
	Metric: z
		.object({
			metricLabel: shortText,
			metricValue: z.union([shortText, z.number().finite()]),
			metricNote: shortText.optional(),
		})
		.strict(),
	KeyValue: z
		.object({
			keyLabel: shortText,
			keyValue: z.union([longText, z.number().finite()]),
		})
		.strict(),
	Progress: z
		.object({
			progressLabel: shortText.optional(),
			value: z.number().finite().min(0).max(100),
			valueLabel: shortText.optional(),
		})
		.strict(),
	WeatherWidget: z
		.object({
			location: z.string().trim().min(1).max(160),
			resolvedLocation: z.string().trim().min(1).max(480).optional(),
			region: optionalPlaceText,
			country: optionalPlaceText,
			confidence: z.number().finite().min(0).max(1).optional(),
			timezone: z.string().trim().min(1).max(120).optional(),
			observedAt: z.string().trim().min(1).max(64).optional(),
			condition: z.string().trim().min(1).max(160),
			summary: longText.optional(),
			weatherCode: z.number().int().min(0).max(99).optional(),
			temperature: z.number().finite().min(-100).max(100).optional(),
			feelsLike: z.number().finite().min(-100).max(100).optional(),
			humidity: z.number().int().min(0).max(100).optional(),
			windSpeed: z.number().finite().min(0).max(500).optional(),
			precipitation: z.number().finite().min(0).max(5_000).optional(),
			isDay: z.boolean().optional(),
			forecast: z.array(forecastDay).max(7).optional(),
			sourceLabel: z.string().trim().min(1).max(120).optional(),
			sources: z.array(weatherSource).max(5).optional(),
			providerLabel: z.string().trim().min(1).max(120).optional(),
		})
		.strict(),
	EstimateGenerationActivity: z
		.object({
			activitySchemaVersion: z.literal("1.0"),
			activityProjectId: z
				.string()
				.regex(/^project_[A-Za-z0-9._~-]{8,96}$/),
			generationRunId: z
				.string()
				.regex(/^run_estimate_generation_[0-9a-f]{32}$/),
			projectCaseVersion: z.number().int().min(1),
		})
		.strict(),
	EstimateEditor: z
		.object({
			schemaId: z.literal("kolibri.estimate_draft"),
			schemaVersion: z.enum(["1.0", "1.1", "1.2", "1.3", "1.4"]),
			projectId: z.string().regex(/^project_[A-Za-z0-9._~-]{8,96}$/),
			documentId: z.string().regex(/^document_[A-Za-z0-9._~-]{8,96}$/),
			version: z.number().int().min(1),
			status: z
				.enum([
					"draft",
					"needs_input",
					"calculating",
					"ready",
					"failed",
					"empty",
					"stale",
					"revoked",
				])
				.transform((value) => {
					if (value === "empty") return "needs_input" as const;
					if (value === "revoked") return "failed" as const;
					if (value === "stale") return "draft" as const;
					return value;
				}),
			requiredFields: z
				.array(z.string().trim().min(1).max(160))
				.max(20)
				.default([]),
			estimateTitle: z.string().trim().min(1).max(240),
			currency: z.literal("RUB"),
			estimateRegion: z
				.string()
				.trim()
				.min(1)
				.max(160)
				.nullable()
				.default(null),
			assumptions: z
				.array(
					z
						.string()
						.trim()
						.min(1)
						.max(KOLIBRI_GENERATIVE_UI_LIMITS.maxPropStringLength),
				)
				.max(20)
				.default([]),
			calculationConditions: z
				.array(
					z.string().trim().min(1).max(KOLIBRI_GENERATIVE_UI_LIMITS.maxPropStringLength),
				)
				.max(20)
				.default([]),
			scopeExclusions: z
				.array(
					z.string().trim().min(1).max(KOLIBRI_GENERATIVE_UI_LIMITS.maxPropStringLength),
				)
				.max(20)
				.default([]),
			commercialTerms: z.record(z.string(), z.unknown()).default({}),
			generation: z
				.object({
					providerProfile: z.string().regex(/^[a-z0-9][a-z0-9._-]{1,95}$/),
					runId: z
						.string()
						.regex(/^(?:run|calculation)_[A-Za-z0-9._~-]{8,96}$/),
					estimateGenerationRunId: z
						.string()
						.trim()
						.min(1)
						.max(160)
						.optional(),
					technologyCardRevisionId: z
						.string()
						.trim()
						.min(1)
						.max(160)
						.optional(),
					technologyCardHash: z
						.string()
						.regex(/^sha256:[0-9a-f]{64}$/)
						.optional(),
					qualityStatus: z.enum(["pending", "failed", "passed"]).optional(),
				})
				.strict()
				.nullable()
				.default(null),
			rows: z.array(estimateRow),
			rowPage: z
				.object({
					offset: z.number().int().min(0).max(1_000_000),
					limit: z.number().int().min(0).max(100),
					totalRows: z.number().int().min(0).max(1_000_000),
					hasMore: z.boolean(),
				})
				.strict()
				.optional(),
			pricing: z
				.object({
					status: z.enum(["unpriced", "partially_sourced", "sourced", "stale"]),
					sourcedRows: z.number().int().min(0),
					staleRows: z.number().int().min(0),
					totalRows: z.number().int().min(0),
					lastCheckedAt: z.string().trim().min(1).max(64).nullable(),
				})
				.strict()
				.default({
					status: "unpriced",
					sourcedRows: 0,
					staleRows: 0,
					totalRows: 0,
					lastCheckedAt: null,
				}),
			totals: z
				.object({
					subtotal: z.string().regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
					total: z.string().regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
				})
				.strict(),
			updatedAt: z.string().trim().min(1).max(64),
		})
		.strict()
		.superRefine((estimate, context) => {
			if (estimate.schemaVersion !== "1.4") return;
			if (!estimate.rowPage) {
				context.addIssue({
					code: "custom",
					message: "Estimate 1.4 requires rowPage metadata.",
					path: ["rowPage"],
				});
				return;
			}
			const { hasMore, limit, offset, totalRows } = estimate.rowPage;
			if (
				estimate.rows.length > limit ||
				offset + estimate.rows.length > totalRows ||
				hasMore !== offset + estimate.rows.length < totalRows ||
				estimate.pricing.totalRows !== totalRows
			) {
				context.addIssue({
					code: "custom",
					message: "Estimate row window metadata is inconsistent.",
					path: ["rowPage"],
				});
			}
		}),
	EstimateDocumentPack: z
		.object({
			schemaId: z.literal("kolibri.estimate-document-pack"),
			schemaVersion: z.literal("1.0"),
			projectId: z.string().regex(/^project_[A-Za-z0-9._~-]{8,96}$/),
			documentId: z.string().regex(/^document_[A-Za-z0-9._~-]{8,96}$/).optional(),
			issueId: z.string().regex(/^estimate_issue_[A-Za-z0-9]{32}$/).optional(),
			estimateVersion: z.number().int().min(0),
			status: z.enum(["needs_input", "failed", "preliminary", "issued", "revoked"]),
			mode: z.enum(["preliminary", "issue"]).optional(),
			documentNumber: z.string().trim().min(1).max(64).optional(),
			rendererVersion: z.string().regex(/^[a-z0-9][a-z0-9._-]{1,63}$/),
			sourceHash: z.string().regex(/^sha256:[0-9a-f]{64}$/).optional(),
			requiredFields: z.array(z.string().trim().min(1).max(240)).max(20).default([]),
			files: z.array(
				z.object({
					artifactId: z.string().regex(/^estimate_artifact_[A-Za-z0-9]{32}$/),
					kind: z.enum(["pdf", "xlsx", "docx", "zip"]),
					filename: z.string().trim().min(1).max(240),
					mediaType: z.string().trim().min(3).max(160),
					sizeBytes: z.number().int().positive().max(52_428_800),
					artifactHash: z.string().regex(/^sha256:[0-9a-f]{64}$/),
					downloadUrl: z.string().regex(/^\/api\/v3\/projects\/project_[A-Za-z0-9._~-]{8,96}\/estimate\/document-pack\/estimate_issue_[A-Za-z0-9]{32}\/artifacts\/estimate_artifact_[A-Za-z0-9]{32}$/),
				})
				.strict(),
			).max(4),
			preview: estimateDocumentPreview.optional(),
		})
		.strict(),
	Divider: z.object({}).strict(),
} as const;

export type KolibriGenerativeUIComponentName =
	keyof typeof kolibriGenerativeUIComponentSchemas;

export const KOLIBRI_GENERATIVE_UI_COMPONENT_NAMES = Object.freeze(
	Object.keys(
		kolibriGenerativeUIComponentSchemas,
	) as KolibriGenerativeUIComponentName[],
);

export const KOLIBRI_GENERATIVE_UI_CONTAINER_NAMES =
	new Set<KolibriGenerativeUIComponentName>(["Card", "Stack", "Grid"]);

export function isKolibriGenerativeUIComponentName(
	value: string,
): value is KolibriGenerativeUIComponentName {
	return Object.hasOwn(kolibriGenerativeUIComponentSchemas, value);
}
