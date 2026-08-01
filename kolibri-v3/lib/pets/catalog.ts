export type PetId =
	| "kolibri"
	| "lumi"
	| "fini"
	| "spark"
	| "dewdrop"
	| "owl"
	| "sprout"
	| "nimbi"
	| "klik"
	| "zumi";

export type PetIdentity = {
	accent: string;
	animation: string;
	assetSlug: string;
	description: string;
	id: PetId;
	moods: readonly [string, string, string, string];
	motionAssetVersion: `v${number}` | null;
	name: string;
	personality: string;
	role: string;
};

export const PET_CATALOG = [
	{
		accent: "#24c7d4",
		animation: "Радостный взмах",
		assetSlug: "kolibri",
		description: "Бирюзовый колибри для быстрых повседневных задач.",
		id: "kolibri",
		moods: ["Готов помочь", "Слушаю задачу", "Уже лечу", "Всё под контролем"],
		motionAssetVersion: "v2",
		name: "Коли",
		personality: "Энергичный и внимательный",
		role: "Универсал",
	},
	{
		accent: "#b6a1f2",
		animation: "Раскрывает крылья",
		assetSlug: "lumi",
		description: "Лунный мотылёк для тихой, глубокой концентрации.",
		id: "lumi",
		moods: [
			"Сохраняю тишину",
			"Фокус включён",
			"Вижу тонкую связь",
			"Мысль стала яснее",
		],
		motionAssetVersion: null,
		name: "Луми",
		personality: "Мягкая и вдумчивая",
		role: "Фокус",
	},
	{
		accent: "#e8b782",
		animation: "Навостряет уши",
		assetSlug: "fini",
		description: "Крылатоухий лисёнок для поиска новых возможностей.",
		id: "fini",
		moods: [
			"Слышу интересное",
			"Проверяю маршрут",
			"Нашёл зацепку",
			"Любопытство ведёт",
		],
		motionAssetVersion: null,
		name: "Фини",
		personality: "Любопытный и находчивый",
		role: "Разведчик",
	},
	{
		accent: "#ff8b3d",
		animation: "Пружинистый рывок",
		assetSlug: "iskra",
		description: "Огненная саламандра для смелого старта и ускорения.",
		id: "spark",
		moods: ["Зажигаем", "Темп набран", "Прорыв рядом", "Энергии хватит"],
		motionAssetVersion: null,
		name: "Искра",
		personality: "Смелая и стремительная",
		role: "Ускоритель",
	},
	{
		accent: "#70d9de",
		animation: "Качает жабрами",
		assetSlug: "runi",
		description: "Аквамариновый аксолотль для спокойной совместной работы.",
		id: "dewdrop",
		moods: ["Не спешим зря", "Разберём по шагам", "Я рядом", "Течение спокойное"],
		motionAssetVersion: null,
		name: "Руни",
		personality: "Терпеливый и добрый",
		role: "Поддержка",
	},
	{
		accent: "#5b5bd6",
		animation: "Вдумчивый наклон",
		assetSlug: "buki",
		description: "Индиговая сова для внимательной проверки деталей.",
		id: "owl",
		moods: [
			"Сверяю детали",
			"Проверяю логику",
			"Есть тонкий нюанс",
			"Теперь аккуратно",
		],
		motionAssetVersion: null,
		name: "Буки",
		personality: "Точный и рассудительный",
		role: "Ревьюер",
	},
	{
		accent: "#79c99a",
		animation: "Тянется ростком",
		assetSlug: "mohi",
		description: "Садовая черепашка для терпеливого развития проектов.",
		id: "sprout",
		moods: [
			"Растём понемногу",
			"Основа крепкая",
			"Ещё один хороший шаг",
			"Проект приживается",
		],
		motionAssetVersion: null,
		name: "Мохи",
		personality: "Надёжный и созидательный",
		role: "Строитель",
	},
	{
		accent: "#72d8f2",
		animation: "Плывёт волной",
		assetSlug: "nimbi",
		description: "Небесный скат-облачко для свободного потока идей.",
		id: "nimbi",
		moods: ["Ловлю идею", "Смотрю шире", "Вариант появился", "Плывём дальше"],
		motionAssetVersion: null,
		name: "Нимби",
		personality: "Мечтательный и изобретательный",
		role: "Идейник",
	},
	{
		accent: "#3a9fa8",
		animation: "Закручивает хвост",
		assetSlug: "klik",
		description: "Механический геккон для точного исполнения шаг за шагом.",
		id: "klik",
		moods: [
			"Контур проверен",
			"Исполняю точно",
			"Механизм работает",
			"Шаг зафиксирован",
		],
		motionAssetVersion: null,
		name: "Клик",
		personality: "Собранный и технический",
		role: "Исполнитель",
	},
	{
		accent: "#f2c84b",
		animation: "Весёлый гул",
		assetSlug: "zumi",
		description: "Солнечный шмель для командного духа и доброго темпа.",
		id: "zumi",
		moods: ["Команда в сборе", "Отличный темп", "Поддерживаю", "У нас получится"],
		motionAssetVersion: null,
		name: "Зуми",
		personality: "Радостный и отзывчивый",
		role: "Мотиватор",
	},
] as const satisfies readonly PetIdentity[];

export const DEFAULT_PET_ID: PetId = "kolibri";

export function getPetIdentity(id: PetId): PetIdentity {
	return PET_CATALOG.find((pet) => pet.id === id) ?? PET_CATALOG[0];
}

export function isPetId(value: unknown): value is PetId {
	return typeof value === "string" && PET_CATALOG.some((pet) => pet.id === value);
}
