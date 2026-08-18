/**
 * Typed contracts for AG-UI `data` parts rendered by the mobile client.
 *
 * The server emits a `data` part with a stable `name`; the client resolves it
 * through a compile-time allowlist (`data.by_name` in `message.tsx`). Unknown
 * names fall back to an explanatory renderer instead of crashing.
 */

export const DATA_PART_NAMES = {
	weather: "weather",
	imageGeneration: "image-generation",
} as const;

export type WeatherForecastRow = {
	readonly day: string;
	readonly highC: number;
	readonly lowC: number;
};

export type WeatherCardData = {
	readonly temperatureC: number;
	readonly condition: string;
	readonly location: string;
	readonly forecast: readonly WeatherForecastRow[];
};

export type ImageGenerationCardData = {
	readonly status: "generating" | "preview" | "complete";
	readonly prompt?: string;
	readonly imageUrl?: string;
	readonly thumbnails?: readonly string[];
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const isFiniteNumber = (value: unknown): value is number =>
	typeof value === "number" && Number.isFinite(value);

const isNonEmptyString = (value: unknown): value is string =>
	typeof value === "string" && value.trim().length > 0;

const isSafeUrl = (value: string) => {
	try {
		const url = new URL(value);
		return url.protocol === "https:" || url.protocol === "http:";
	} catch {
		return false;
	}
};

export const parseWeatherCard = (value: unknown): WeatherCardData | null => {
	if (
		!isRecord(value) ||
		!isFiniteNumber(value.temperatureC) ||
		!isNonEmptyString(value.condition) ||
		!isNonEmptyString(value.location) ||
		!Array.isArray(value.forecast)
	) {
		return null;
	}
	const forecast: WeatherForecastRow[] = [];
	for (const row of value.forecast) {
		if (
			!isRecord(row) ||
			!isNonEmptyString(row.day) ||
			!isFiniteNumber(row.highC) ||
			!isFiniteNumber(row.lowC)
		) {
			return null;
		}
		forecast.push({
			day: row.day,
			highC: row.highC,
			lowC: row.lowC,
		});
	}
	if (forecast.length === 0) return null;
	return {
		temperatureC: value.temperatureC,
		condition: value.condition,
		location: value.location,
		forecast,
	};
};

export const parseImageGenerationCard = (
	value: unknown,
): ImageGenerationCardData | null => {
	if (
		!isRecord(value) ||
		(value.status !== "generating" &&
			value.status !== "preview" &&
			value.status !== "complete")
	) {
		return null;
	}
	const prompt = isNonEmptyString(value.prompt) ? value.prompt : undefined;
	const imageUrl =
		isNonEmptyString(value.imageUrl) && isSafeUrl(value.imageUrl)
			? value.imageUrl
			: undefined;
	const thumbnails = Array.isArray(value.thumbnails)
		? value.thumbnails.filter(
				(item): item is string =>
					isNonEmptyString(item) && isSafeUrl(item),
			)
		: undefined;
	return {
		status: value.status,
		prompt,
		imageUrl,
		thumbnails: thumbnails && thumbnails.length > 0 ? thumbnails : undefined,
	};
};
