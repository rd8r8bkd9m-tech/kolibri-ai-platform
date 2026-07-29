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

const optionalPlaceText = z
  .string()
  .trim()
  .max(160)
  .optional();

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
      .enum(["work", "material", "equipment", "service"])
      .default("service"),
    description: z.string().trim().min(1).max(300),
    unit: z.string().trim().min(1).max(32),
    quantity: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/),
    unitPrice: z.string().regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/),
    lineTotal: z.string().regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
    quantityBasis: z
      .string()
      .trim()
      .min(1)
      .max(500)
      .default("Введено вручную"),
    priceBasis: z
      .string()
      .trim()
      .min(1)
      .max(500)
      .default("Введено вручную"),
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
        unitPrice: z
          .string()
          .regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
        deliveryPerUnit: z
          .string()
          .regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
        landedUnitPrice: z
          .string()
          .regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
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
        unitPrice: z
          .string()
          .regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{2})$/),
        currency: z.literal("RUB"),
        vatMode: z.enum([
          "included",
          "excluded",
          "not_applicable",
          "unknown",
        ]),
        confidence: z
          .string()
          .regex(/^(?:0(?:\.\d{1,6})?|1(?:\.0{1,6})?)$/),
      })
      .strict()
      .optional(),
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
      region: optionalPlaceText,
      country: optionalPlaceText,
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
  EstimateEditor: z
    .object({
      schemaId: z.literal("kolibri.estimate_draft"),
      schemaVersion: z.enum(["1.0", "1.1", "1.2"]),
      projectId: z.string().regex(/^project_[A-Za-z0-9._~-]{8,96}$/),
      documentId: z.string().regex(/^document_[A-Za-z0-9._~-]{8,96}$/),
      version: z.number().int().min(1),
      status: z.enum(["empty", "draft", "ready", "stale", "revoked"]),
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
      generation: z
        .object({
          providerProfile: z.enum([
            "mimo-code",
            "codex-cli",
            "estimate-engine",
          ]),
          runId: z
            .string()
            .regex(/^(?:run|calculation)_[A-Za-z0-9._~-]{8,96}$/),
        })
        .strict()
        .nullable()
        .default(null),
      rows: z.array(estimateRow).max(200),
      pricing: z
        .object({
          status: z.enum([
            "unpriced",
            "partially_sourced",
            "sourced",
            "stale",
          ]),
          sourcedRows: z.number().int().min(0).max(200),
          staleRows: z.number().int().min(0).max(200),
          totalRows: z.number().int().min(0).max(200),
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
          subtotal: z
            .string()
            .regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
          total: z
            .string()
            .regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
        })
        .strict(),
      updatedAt: z.string().trim().min(1).max(64),
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

export const KOLIBRI_GENERATIVE_UI_CONTAINER_NAMES = new Set<
  KolibriGenerativeUIComponentName
>(["Card", "Stack", "Grid"]);

export function isKolibriGenerativeUIComponentName(
  value: string,
): value is KolibriGenerativeUIComponentName {
  return Object.hasOwn(kolibriGenerativeUIComponentSchemas, value);
}
