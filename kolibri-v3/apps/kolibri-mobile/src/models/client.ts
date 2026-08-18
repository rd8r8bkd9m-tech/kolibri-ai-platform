// Mobile mirror of the shared model-catalog contract. The web app fetches the
// catalog through the Next BFF; the mobile PWA/native client talks to
// /v1/models/* directly through the product gateway, so this module keeps its
// own strict parser aligned with the backend ModelCatalogView payload.

export type MobileModel = {
	id: string;
	profile: string;
	displayName: string;
	description: string;
	available: boolean;
	isDefault: boolean;
};

export type MobileCatalogProfile = {
	id: string;
	displayName: string;
	available: boolean;
	modelSelectionSupported: boolean;
};

export type MobileModelCatalog = {
	models: MobileModel[];
	profiles: MobileCatalogProfile[];
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const SAFE_MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;
const SAFE_PROFILE_ID = /^[a-z0-9][a-z0-9._-]{1,95}$/;

function text(
	value: unknown,
	pattern: RegExp,
	maximum: number,
): string | null {
	if (typeof value !== "string" || value.length > maximum) return null;
	return pattern.test(value) ? value : null;
}

function boolean(value: unknown): boolean | null {
	return typeof value === "boolean" ? value : null;
}

function parseModel(value: unknown): MobileModel | null {
	if (!isRecord(value)) return null;
	const id = text(value.id, SAFE_MODEL_ID, 120);
	const profile = text(value.profile, SAFE_PROFILE_ID, 96);
	if (!id || !profile) return null;
	const displayName = text(value.displayName, /^[\s\S]{1,120}$/, 120);
	if (!displayName) return null;
	const available = boolean(value.available);
	const isDefault = boolean(value.isDefault);
	if (available === null || isDefault === null) return null;
	return {
		id,
		profile,
		displayName,
		description: typeof value.description === "string" ? value.description : "",
		available,
		isDefault,
	};
}

function parseProfile(value: unknown): MobileCatalogProfile | null {
	if (!isRecord(value)) return null;
	const id = text(value.id, SAFE_PROFILE_ID, 96);
	const displayName = text(value.displayName, /^[\s\S]{1,120}$/, 120);
	if (!id || !displayName) return null;
	const available = boolean(value.available);
	const modelSelectionSupported = boolean(value.modelSelectionSupported);
	if (available === null || modelSelectionSupported === null) return null;
	return { id, displayName, available, modelSelectionSupported };
}

export function parseMobileCatalog(value: unknown): MobileModelCatalog | null {
	if (
		!isRecord(value) ||
		!Array.isArray(value.models) ||
		!Array.isArray(value.profiles)
	) {
		return null;
	}
	const models = value.models
		.slice(0, 100)
		.map(parseModel)
		.filter((model): model is MobileModel => model !== null);
	const profiles = value.profiles
		.slice(0, 100)
		.map(parseProfile)
		.filter((profile): profile is MobileCatalogProfile => profile !== null);
	if (!models.some((model) => model.id === "auto")) return null;
	return { models, profiles };
}

export class MobileModelClient {
	constructor(
		private readonly authorizedFetch: typeof fetch,
		private readonly apiBaseUrl: string,
	) {}

	async catalog(): Promise<MobileModelCatalog> {
		const response = await this.authorizedFetch(
			`${this.apiBaseUrl}/v1/models/catalog`,
			{ headers: { Accept: "application/json" }, cache: "no-store" },
		);
		let payload: unknown = null;
		try {
			payload = await response.json();
		} catch {
			payload = null;
		}
		if (!response.ok) {
			throw new Error(
				isRecord(payload) && typeof payload.message === "string"
					? payload.message
					: "Каталог моделей сейчас недоступен.",
			);
		}
		const catalog = parseMobileCatalog(payload);
		if (!catalog) {
			throw new Error("Backend вернул некорректный каталог моделей.");
		}
		return catalog;
	}

	async saveSettings(input: {
		profile: string;
		model: string | null;
		reasoningEffort?: string | null;
		serviceTier?: string | null;
	}): Promise<void> {
		const response = await this.authorizedFetch(
			`${this.apiBaseUrl}/v1/profile/model-settings`,
			{
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					profile: input.profile,
					model: input.model,
					reasoningEffort: input.reasoningEffort ?? null,
					serviceTier: input.serviceTier ?? null,
				}),
			},
		);
		if (!response.ok) {
			let message = "Не удалось сохранить модель.";
			try {
				const payload = (await response.json()) as Record<string, unknown>;
				if (typeof payload.message === "string") message = payload.message;
			} catch {
				// keep the default message
			}
			throw new Error(message);
		}
	}
}

export function effectiveMobileModelName(
	catalog: MobileModelCatalog | null,
	preferredProfile: string | null,
	preferredModel: string | null,
): string {
	if (preferredModel) {
		const exact = catalog?.models.find((model) => model.id === preferredModel);
		if (exact) return exact.displayName;
		const suffixed = preferredModel.match(
			/^(?:platform|user):[A-Za-z0-9._:-]{1,8}:(.+)$/,
		);
		const slug = suffixed ? suffixed[1] : preferredModel;
		const bySlug = catalog?.models.find(
			(model) => model.id === slug || model.id.endsWith(`:${slug}`),
		);
		if (bySlug) return bySlug.displayName;
		const cleaned = slug.replace(/[._-]+/g, " ").trim();
		return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : slug;
	}
	if (!catalog) return "Авто";
	if (preferredProfile && preferredProfile !== "auto") {
		const profile = catalog.profiles.find((p) => p.id === preferredProfile);
		if (profile) return profile.displayName;
	}
	return "Авто";
}
