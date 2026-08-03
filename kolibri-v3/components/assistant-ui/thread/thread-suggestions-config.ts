import {
	Globe2Icon,
	ImageIcon,
	PencilIcon,
	type LucideIcon,
} from "lucide-react";

type StarterAction = {
	label: string;
	prompt: string;
	icon: LucideIcon;
	send: boolean;
};

type DesktopStarterAction = {
	title: string;
	description: string;
	ariaLabel: string;
	prompt: string;
};

export const MOBILE_STARTERS: readonly StarterAction[] = [
	{
		label: "Создать изображение",
		prompt:
			"Создай изображение по моему описанию. Сначала уточни стиль, формат и назначение.",
		icon: ImageIcon,
		send: true,
	},
	{
		label: "Напиши или отредактируй",
		prompt:
			"Помоги написать или отредактировать текст. Сначала уточни тип текста, аудиторию и желаемый результат.",
		icon: PencilIcon,
		send: false,
	},
	{
		label: "Искать в интернете",
		prompt:
			"Найди актуальную информацию в интернете по моему запросу и приложи источники.",
		icon: Globe2Icon,
		send: false,
	},
] as const;

export const DESKTOP_STARTERS: readonly DesktopStarterAction[] = [
	{
		title: "Рассчитать смету",
		description: "По описанию объекта",
		ariaLabel: "Рассчитать смету по описанию объекта",
		prompt:
			"Подготовь подробную предварительную смету по моему описанию объекта. Сначала выдели исходные данные и условия расчёта. Раздели работы, материалы, оборудование и услуги на отдельные позиции.",
	},
	{
		title: "Спланировать проект",
		description: "От цели до результата",
		ariaLabel: "Спланировать проект от цели до результата",
		prompt:
			"Составь план проекта: этапы, зависимости, сроки, риски и необходимые исходные данные.",
	},
	{
		title: "Подготовить документ",
		description: "КП, договор или отчёт",
		ariaLabel: "Подготовить проектный документ",
		prompt:
			"Помоги подготовить проектный документ. Уточни тип документа, назначение и обязательные реквизиты.",
	},
	{
		title: "Проверить основания",
		description: "Источники и доказательства",
		ariaLabel: "Проверить источники и доказательства",
		prompt:
			"Проверь исходные данные и выводы: покажи источники, условия расчёта, версии и недостающие доказательства.",
	},
];
