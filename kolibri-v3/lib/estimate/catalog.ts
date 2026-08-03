import { withCsrfHeader } from "@/lib/csrf";

export type CatalogAutocompleteEntry = {
	id: string;
	kind:
		| "work"
		| "material"
		| "equipment"
		| "service"
		| "overhead"
		| "tax"
		| "contingency";
	canonicalName: string;
	shortName: string;
	canonicalUnit: string;
	categoryId: string;
	version: number;
	description: string;
	confidence: string;
	visibility: "project_private" | "tenant_private" | "system_curated" | "market_aggregate";
	priceRange: {
		p25: string;
		median: string;
		p75: string;
		freshness: string;
		confidence: string;
		generatedAt: string;
	} | null;
};

const isCatalogEntry = (value: unknown): value is CatalogAutocompleteEntry => {
	if (typeof value !== "object" || value === null) return false;
	const entry = value as Record<string, unknown>;
	return (
		typeof entry.id === "string" &&
		typeof entry.canonicalName === "string" &&
		typeof entry.canonicalUnit === "string" &&
		[
			"work",
			"material",
			"equipment",
			"service",
			"overhead",
			"tax",
			"contingency",
		].includes(String(entry.kind))
	);
};

export async function searchEstimateCatalog(
	projectId: string,
	query: string,
	region: string | undefined,
	signal?: AbortSignal,
): Promise<CatalogAutocompleteEntry[]> {
	const params = new URLSearchParams({ query: query.trim(), limit: "8" });
	if (region?.trim()) params.set("region", region.trim());
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(projectId)}/estimate/catalog?${params.toString()}`,
		{
			headers: { Accept: "application/json" },
			credentials: "same-origin",
			cache: "no-store",
			signal,
		},
	);
	if (!response.ok) throw new Error("Не удалось загрузить справочник.");
	const value: unknown = await response.json();
	if (typeof value !== "object" || value === null) return [];
	const entries = (value as { entries?: unknown }).entries;
	return Array.isArray(entries) ? entries.filter(isCatalogEntry) : [];
}

export async function createEstimateCatalogCandidate(
	projectId: string,
	input: {
		originalText: string;
		kind: CatalogAutocompleteEntry["kind"];
		proposedUnit: string;
	},
): Promise<void> {
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(projectId)}/estimate/catalog`,
		{
			method: "POST",
			headers: withCsrfHeader({
				Accept: "application/json",
				"Content-Type": "application/json",
				"Idempotency-Key": `catalog-candidate-${globalThis.crypto.randomUUID()}`,
			}),
			credentials: "same-origin",
			cache: "no-store",
			body: JSON.stringify({
				originalText: input.originalText,
				proposedCanonicalName: input.originalText,
				proposedShortName: input.originalText.slice(0, 160),
				kind: input.kind,
				proposedUnit: input.proposedUnit.trim() || "шт.",
				sourceType: "user_manual",
				confidence: "0",
			}),
		},
	);
	if (!response.ok) throw new Error("Не удалось отправить позицию на проверку.");
}
