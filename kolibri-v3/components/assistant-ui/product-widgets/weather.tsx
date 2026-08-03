"use client";

import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import {
	CloudFogIcon,
	CloudIcon,
	CloudLightningIcon,
	CloudRainIcon,
	CloudSnowIcon,
	SnowflakeIcon,
	MoonStarIcon,
	SunIcon,
	WindIcon,
	DropletsIcon,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";
import {
	type WeatherScene,
	type WeatherWidgetProps,
} from "./types";

const WEATHER_ICONS: ReadonlyArray<{
	readonly codes: readonly number[];
	readonly icon: (props: React.ComponentProps<"svg">) => React.ReactNode;
}> = [
	{ codes: [0, 1], icon: SunIcon },
	{ codes: [45, 48], icon: CloudFogIcon },
	{
		codes: [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82],
		icon: CloudRainIcon,
	},
	{ codes: [71, 73, 75, 77, 85, 86], icon: CloudSnowIcon },
	{ codes: [95, 96, 99], icon: CloudLightningIcon },
];

const RAIN_CODES = new Set([
	51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82,
]);
const SNOW_CODES = new Set([71, 73, 75, 77, 85, 86]);
const STORM_CODES = new Set([95, 96, 99]);
const CLOUD_CODES = new Set([2, 3, 45, 48]);

const weatherSceneFor = (
	code: number | undefined,
	condition: string,
	isDay: boolean | undefined,
): WeatherScene => {
	if (typeof code === "number") {
		if (STORM_CODES.has(code)) return "storm";
		if (SNOW_CODES.has(code)) return "snow";
		if (RAIN_CODES.has(code)) return "rain";
		if (CLOUD_CODES.has(code)) return "clouds";
		if (code === 0 || code === 1) {
			return isDay === false ? "clear-night" : "clear-day";
		}
	}

	const normalized = condition.toLocaleLowerCase("ru-RU");
	if (/(гроз|thunder)/.test(normalized)) return "storm";
	if (/(снег|snow)/.test(normalized)) return "snow";
	if (/(дожд|лив|морос|rain|shower|drizzle)/.test(normalized)) {
		return "rain";
	}
	if (/(облач|пасмур|туман|cloud|overcast|fog|mist)/.test(normalized)) {
		return "clouds";
	}
	return isDay === false ? "clear-night" : "clear-day";
};

const WEATHER_SCENE_ASSET: Record<WeatherScene, string> = {
	"clear-day": "/weather/clear-day.webp",
	"clear-night": "/weather/clear-night.webp",
	clouds: "/weather/overcast.webp",
	rain: "/weather/storm-rain.webp",
	snow: "/weather/overcast.webp",
	storm: "/weather/storm-rain.webp",
};

function WeatherSceneBackdrop({
	active,
	scene,
}: {
	active: boolean;
	scene: WeatherScene;
}) {
	const hasRain = scene === "rain" || scene === "storm";

	return (
		<div
			aria-hidden="true"
			className="kolibri-weather-scene absolute inset-0 -z-20 overflow-hidden"
			data-weather-active={active ? "true" : "false"}
			data-weather-scene={scene}
		>
			<Image
				alt=""
				className="kolibri-weather-scene__backdrop absolute inset-0 size-full object-cover"
				fill
				loading="eager"
				sizes="(max-width: 640px) 100vw, 760px"
				src={WEATHER_SCENE_ASSET[scene]}
			/>

			{hasRain ? (
				<Image
					alt=""
					className="kolibri-weather-scene__rain absolute inset-0 size-full object-cover"
					fill
					sizes="(max-width: 640px) 100vw, 760px"
					src="/weather/storm-rain.webp"
				/>
			) : null}

			{scene === "clear-day" ? (
				<SunIcon className="kolibri-weather-scene__sun absolute right-[7%] top-[8%] size-24 stroke-[0.7] text-amber-100/75 sm:size-32" />
			) : null}

			{scene === "clear-night" ? (
				<MoonStarIcon className="kolibri-weather-scene__moon absolute right-[8%] top-[9%] size-20 stroke-[0.8] text-slate-100/80 sm:size-28" />
			) : null}

			{scene === "snow" ? (
				<>
					<SnowflakeIcon className="kolibri-weather-scene__snow kolibri-weather-scene__snow--one absolute left-[13%] top-[-12%] size-6 stroke-[1] text-white/70" />
					<SnowflakeIcon className="kolibri-weather-scene__snow kolibri-weather-scene__snow--two absolute left-[53%] top-[-16%] size-6 stroke-[0.8] text-white/55" />
					<SnowflakeIcon className="kolibri-weather-scene__snow kolibri-weather-scene__snow--three absolute left-[82%] top-[-10%] size-5 stroke-[1] text-white/65" />
				</>
			) : null}

			{scene === "storm" ? (
				<div className="kolibri-weather-scene__flash absolute inset-0 bg-white" />
			) : null}
		</div>
	);
}

const iconForWeather = (code?: number, condition = "") => {
	const coded = WEATHER_ICONS.find(({ codes }) =>
		typeof code === "number" ? codes.includes(code) : false,
	)?.icon;
	if (coded) return coded;

	const normalized = condition.toLocaleLowerCase("ru-RU");
	if (/(гроз|thunder)/.test(normalized)) return CloudLightningIcon;
	if (/(снег|snow)/.test(normalized)) return CloudSnowIcon;
	if (/(дожд|лив|морос|rain|shower|drizzle)/.test(normalized)) {
		return CloudRainIcon;
	}
	if (/(туман|fog|mist)/.test(normalized)) return CloudFogIcon;
	if (/(ясн|солнеч|clear|sunny)/.test(normalized)) return SunIcon;
	return CloudIcon;
};

const formatTemperature = (value: number) => `${Math.round(value)}°`;

const formatForecastDay = (date: string, index: number) => {
	if (index === 0) return "Сегодня";
	if (index === 1) return "Завтра";
	const parsed = new Date(`${date}T12:00:00`);
	if (!Number.isFinite(parsed.valueOf())) return date;
	return new Intl.DateTimeFormat("ru-RU", { weekday: "short" })
		.format(parsed)
		.replace(".", "");
};

const formatObservedAt = (value: string) => {
	const parsed = new Date(value);
	if (!Number.isFinite(parsed.valueOf())) return value;
	return new Intl.DateTimeFormat("ru-RU", {
		day: "numeric",
		month: "long",
		hour: "2-digit",
		minute: "2-digit",
	}).format(parsed);
};

export function WeatherWidget(props: WeatherWidgetProps) {
	const widgetRef = useRef<HTMLElement>(null);
	const [sceneActive, setSceneActive] = useState(false);
	const CurrentIcon = iconForWeather(props.weatherCode, props.condition);
	const scene = weatherSceneFor(
		props.weatherCode,
		props.condition,
		props.isDay,
	);
	const forecast = props.forecast ?? [];
	const today = forecast[0];
	const hasDetails =
		props.feelsLike !== undefined ||
		props.humidity !== undefined ||
		props.windSpeed !== undefined ||
		props.precipitation !== undefined;
	const placeDetails = [props.region, props.country]
		.filter((value) => value && value !== props.location)
		.join(", ");

	useEffect(() => {
		const widget = widgetRef.current;
		if (!widget || typeof IntersectionObserver === "undefined") {
			setSceneActive(true);
			return;
		}

		const observer = new IntersectionObserver(
			(entries) => {
				const [entry] = entries;
				if (entry) setSceneActive(entry.isIntersecting);
			},
			{ rootMargin: "180px 0px" },
		);
		observer.observe(widget);
		return () => observer.disconnect();
	}, []);

	return (
		<section
			className="relative isolate overflow-hidden rounded-[28px] border border-white/10 bg-[#05080d] text-white shadow-[0_18px_50px_rgba(2,6,23,0.18)]"
			aria-label={`Погода: ${props.location}`}
			data-weather-active={sceneActive ? "true" : "false"}
			ref={widgetRef}
		>
			<WeatherSceneBackdrop active={sceneActive} scene={scene} />
			<div
				aria-hidden="true"
				className={`absolute inset-0 -z-10 ${
					scene === "clear-day" ? "bg-slate-950/35" : "bg-black/40"
				}`}
			/>

			<div className="flex min-h-[440px] flex-col p-5 sm:min-h-[540px] sm:p-8">
				<header className="flex min-w-0 items-start justify-between gap-4">
					<div className="min-w-0">
						<h3 className="truncate text-2xl font-medium tracking-[-0.025em] sm:text-[28px]">
							{props.location}
						</h3>
						<p className="mt-1 truncate text-sm text-white/65">
							{[placeDetails, props.condition].filter(Boolean).join(" · ")}
						</p>
					</div>
					<CurrentIcon
						aria-hidden="true"
						className={`kolibri-weather-current-icon mt-1 size-7 shrink-0 stroke-[1.35] text-white/80 ${
							scene === "clear-day"
								? "kolibri-weather-current-icon--spin"
								: "kolibri-weather-current-icon--float"
						}`}
					/>
				</header>

				<div className="mt-5 min-w-0 sm:mt-6">
					{props.temperature !== undefined ? (
						<div className="flex items-start">
							<span className="text-[88px] font-light leading-[0.88] tracking-[-0.075em] tabular-nums sm:text-[112px]">
								{Math.round(props.temperature)}
							</span>
							<span className="ml-2 mt-1 text-[34px] font-light tracking-[-0.04em] text-white/80 sm:mt-2 sm:text-[42px]">
								°C
							</span>
						</div>
					) : (
						<p className="text-4xl font-light tracking-tight">
							{props.condition}
						</p>
					)}

					{today?.temperatureMax !== undefined ||
					today?.temperatureMin !== undefined ? (
						<div className="mt-5 flex items-center gap-4 text-xl font-medium tabular-nums sm:text-2xl">
							{today.temperatureMax !== undefined ? (
								<span>
									<span className="mr-2 font-normal text-white/45">H</span>
									{formatTemperature(today.temperatureMax)}
								</span>
							) : null}
							{today.temperatureMin !== undefined ? (
								<span>
									<span className="mr-2 font-normal text-white/45">L</span>
									{formatTemperature(today.temperatureMin)}
								</span>
							) : null}
						</div>
					) : null}

					{hasDetails ? (
						<dl className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-white/60 sm:text-sm">
							{props.feelsLike !== undefined ? (
								<div className="flex items-center gap-1.5">
									<dt>Ощущается</dt>
									<dd className="font-medium text-white/90 tabular-nums">
										{formatTemperature(props.feelsLike)}
									</dd>
								</div>
							) : null}
							{props.humidity !== undefined ? (
								<div className="flex items-center gap-1.5">
									<dt className="flex items-center gap-1">
										<DropletsIcon aria-hidden="true" className="size-3.5" />
										Влажность
									</dt>
									<dd className="font-medium text-white/90 tabular-nums">
										{props.humidity}%
									</dd>
								</div>
							) : null}
							{props.windSpeed !== undefined ? (
								<div className="flex items-center gap-1.5">
									<dt className="flex items-center gap-1">
										<WindIcon aria-hidden="true" className="size-3.5" />
										Ветер
									</dt>
									<dd className="font-medium text-white/90 tabular-nums">
										{props.windSpeed} км/ч
									</dd>
								</div>
							) : null}
							{props.precipitation !== undefined ? (
								<div className="flex items-center gap-1.5">
									<dt>Осадки</dt>
									<dd className="font-medium text-white/90 tabular-nums">
										{props.precipitation} мм
									</dd>
								</div>
							) : null}
						</dl>
					) : null}

					{props.summary ? <p className="sr-only">{props.summary}</p> : null}
				</div>

				{forecast.length > 0 ? (
					<div className="mt-auto overflow-x-auto rounded-[24px] border border-white/10 bg-[#080b14]/80 px-2 py-5 sm:px-3 sm:py-6">
						<div className="grid min-w-[470px] grid-flow-col auto-cols-fr">
							{forecast.map((day, index) => {
								const ForecastIcon = iconForWeather(
									day.weatherCode,
									day.condition,
								);
								return (
									<div
										key={day.date}
										className="flex min-w-[86px] flex-col items-center px-2 text-center"
									>
										<p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/85 sm:text-xs">
											{formatForecastDay(day.date, index)}
										</p>
										<ForecastIcon
											aria-hidden="true"
											className="my-3 size-6 stroke-[1.35] text-white/75 sm:size-7"
										/>
										{day.temperatureMax !== undefined ||
										day.temperatureMin !== undefined ? (
											<div className="tabular-nums">
												<p className="text-lg font-medium sm:text-xl">
													{day.temperatureMax !== undefined
														? formatTemperature(day.temperatureMax)
														: "—"}
												</p>
												<p className="mt-0.5 text-sm font-normal text-white/65 sm:text-base">
													{day.temperatureMin !== undefined
														? formatTemperature(day.temperatureMin)
														: "—"}
												</p>
											</div>
										) : (
											<p className="max-w-20 truncate text-xs font-medium text-white/85">
												{day.condition}
											</p>
										)}
									</div>
								);
							})}
						</div>
					</div>
				) : null}

				{props.observedAt ||
				props.sourceLabel ||
				(props.sources && props.sources.length > 0) ? (
					<footer className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-[10px] text-white/45">
						<span>
							{props.observedAt
								? `Данные на ${formatObservedAt(props.observedAt)}`
								: "Ответ выбранной модели"}
						</span>
						<span className="flex flex-wrap items-center gap-x-3 gap-y-1">
							{props.sources?.map((source) =>
								source.sourceUrl ? (
									<a
										key={`${source.label}-${source.sourceUrl}`}
										className="rounded underline-offset-4 hover:text-white/80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
										href={source.sourceUrl}
										target="_blank"
										rel="noreferrer"
									>
										{source.label}
									</a>
								) : (
									<span key={source.label}>{source.label}</span>
								),
							)}
							{props.sourceLabel ? (
								<a
									className="rounded underline-offset-4 hover:text-white/80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
									href="https://open-meteo.com/"
									target="_blank"
									rel="noreferrer"
								>
									{props.sourceLabel}
								</a>
							) : null}
						</span>
					</footer>
				) : null}
			</div>
		</section>
	);
}

type WeatherToolArgs = {
	readonly location?: unknown;
	readonly forecastDays?: unknown;
};

export const WeatherToolUI: ToolCallMessagePartComponent<
	WeatherToolArgs,
	unknown
> = ({ args, result, status }) => {
		if (status.type === "running") {
			return (
				<div
					className="rounded-xl border border-border px-4 py-3 text-sm text-muted-foreground"
					role="status"
					aria-live="polite"
				>
					Получаю погоду для{" "}
					{typeof args.location === "string" ? args.location : "города"}…
				</div>
			);
		}

		let decodedResult: unknown = result;
		if (typeof result === "string") {
			try {
				decodedResult = JSON.parse(result) as unknown;
			} catch {
				decodedResult = null;
			}
		}
		if (
			typeof decodedResult === "object" &&
			decodedResult !== null &&
			!Array.isArray(decodedResult) &&
			"$type" in decodedResult &&
			decodedResult.$type === "WeatherWidget"
		) {
			const { $type: _type, ...weatherProps } = decodedResult;
			decodedResult = weatherProps;
		}
		const parsed =
			kolibriGenerativeUIComponentSchemas.WeatherWidget.safeParse(
				decodedResult,
			);
		if (!parsed.success) {
			return (
				<div
					className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted-foreground"
					role="alert"
				>
					Погодный сервис вернул данные неизвестного формата.
				</div>
			);
		}
		return <WeatherWidget {...parsed.data} />;
};
