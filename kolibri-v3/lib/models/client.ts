"use client";

import {
  isAgentProfile,
  type AgentProfile,
} from "@/lib/identity/contracts";

export type ReasoningEffortOption = {
  id: string;
  description: string;
};

export type ServiceTierOption = {
  id: string;
  name: string;
  description: string;
};

export type CatalogModel = {
  id: string;
  profile: AgentProfile;
  displayName: string;
  description: string;
  available: boolean;
  supportedReasoningEfforts: ReasoningEffortOption[];
  serviceTiers: ServiceTierOption[];
  defaultReasoningEffort: string | null;
  isDefault: boolean;
  upgrade: string | null;
};

export type ModelCatalog = {
  models: CatalogModel[];
  codexCatalogAvailable: boolean;
  configuredCodexModel: string | null;
  configuredCodexEffort: string | null;
};

const SAFE_MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
const SAFE_EFFORT = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const SAFE_SERVICE_TIER = /^[a-z0-9][a-z0-9_-]{0,31}$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function optionalText(
  value: unknown,
  pattern: RegExp,
): string | null | undefined {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  return pattern.test(normalized) ? normalized : undefined;
}

function boundedText(value: unknown, limit: number) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized && normalized.length <= limit ? normalized : null;
}

function parseModel(value: unknown): CatalogModel | null {
  if (!isRecord(value)) return null;
  const rawServiceTiers = value.serviceTiers ?? [];
  const id = optionalText(value.id, SAFE_MODEL_ID);
  const displayName = boundedText(value.displayName, 120);
  const description = boundedText(value.description, 500) ?? "";
  const defaultReasoningEffort = optionalText(
    value.defaultReasoningEffort,
    SAFE_EFFORT,
  );
  const upgrade = optionalText(value.upgrade, SAFE_MODEL_ID);
  if (
    !id ||
    !displayName ||
    !isAgentProfile(value.profile) ||
    typeof value.available !== "boolean" ||
    !Array.isArray(value.supportedReasoningEfforts) ||
    !Array.isArray(rawServiceTiers) ||
    defaultReasoningEffort === undefined ||
    upgrade === undefined
  ) {
    return null;
  }

  const efforts: ReasoningEffortOption[] = [];
  for (const raw of value.supportedReasoningEfforts.slice(0, 16)) {
    if (!isRecord(raw)) continue;
    const effortId = optionalText(raw.id, SAFE_EFFORT);
    if (!effortId || efforts.some((item) => item.id === effortId)) continue;
    efforts.push({
      id: effortId,
      description: boundedText(raw.description, 240) ?? "",
    });
  }
  const serviceTiers: ServiceTierOption[] = [];
  for (const raw of rawServiceTiers.slice(0, 8)) {
    if (!isRecord(raw)) continue;
    const tierId = optionalText(raw.id, SAFE_SERVICE_TIER);
    const name = boundedText(raw.name, 80);
    if (
      !tierId ||
      !name ||
      serviceTiers.some((item) => item.id === tierId)
    ) {
      continue;
    }
    serviceTiers.push({
      id: tierId,
      name,
      description: boundedText(raw.description, 240) ?? "",
    });
  }
  if (
    defaultReasoningEffort !== null &&
    !efforts.some((item) => item.id === defaultReasoningEffort)
  ) {
    return null;
  }
  return {
    id,
    profile: value.profile,
    displayName,
    description,
    available: value.available,
    supportedReasoningEfforts: efforts,
    serviceTiers,
    defaultReasoningEffort,
    isDefault: value.isDefault === true,
    upgrade,
  };
}

function parseCatalog(value: unknown): ModelCatalog | null {
  if (
    !isRecord(value) ||
    !Array.isArray(value.models) ||
    typeof value.codexCatalogAvailable !== "boolean"
  ) {
    return null;
  }
  const configuredCodexModel = optionalText(
    value.configuredCodexModel,
    SAFE_MODEL_ID,
  );
  const configuredCodexEffort = optionalText(
    value.configuredCodexEffort,
    SAFE_EFFORT,
  );
  if (
    configuredCodexModel === undefined ||
    configuredCodexEffort === undefined
  ) {
    return null;
  }
  const models = value.models
    .slice(0, 100)
    .map(parseModel)
    .filter((model): model is CatalogModel => model !== null);
  if (!models.some((model) => model.id === "auto")) return null;
  return {
    models,
    codexCatalogAvailable: value.codexCatalogAvailable,
    configuredCodexModel,
    configuredCodexEffort,
  };
}

export async function getModelCatalog(
  signal?: AbortSignal,
): Promise<ModelCatalog> {
  const response = await fetch("/api/v3/models/catalog", {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message =
      isRecord(payload) && typeof payload.message === "string"
        ? payload.message
        : "Каталог моделей сейчас недоступен.";
    throw new Error(message);
  }
  const catalog = parseCatalog(payload);
  if (!catalog) {
    throw new Error("Backend вернул некорректный каталог моделей.");
  }
  return catalog;
}
