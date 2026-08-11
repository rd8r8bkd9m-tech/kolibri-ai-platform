"use client";

import {
	ComposerPrimitive,
	unstable_useMentionAdapter,
	unstable_useSlashCommandAdapter,
	useAui,
	type Unstable_SlashCommand,
} from "@assistant-ui/react";
import { useMemo } from "react";

const SLASH_COMMANDS = [
	{
		id: "estimate",
		label: "Создать смету",
		description: "Собрать смету по описанию работ",
		prompt: "Создай смету на: ",
	},
	{
		id: "document",
		label: "Документ",
		description: "Подготовить КП, акт, договор или письмо",
		prompt: "Подготовь документ: ",
	},
	{
		id: "calculate",
		label: "Расчёт",
		description: "Выполнить детерминированный расчёт с проверяемым результатом",
		prompt: "Выполни расчёт: ",
	},
	{
		id: "search",
		label: "Справочники",
		description: "Найти нормативы и цены в доступных справочниках",
		prompt: "Найди в справочниках: ",
	},
	{
		id: "export",
		label: "Экспорт",
		description: "Выгрузить результат в XLSX, PDF или DOCX",
		prompt: "Экспортируй результат в: ",
	},
] as const;

const TRIGGER_POPOVER_CLASS =
	"absolute bottom-full left-0 z-50 mb-2 max-h-72 w-full overflow-y-auto rounded-xl border border-border/70 bg-popover p-1 shadow-[0_16px_40px_-20px_rgba(0,0,0,0.45)]";

function TriggerItemRow({
	item,
	index,
}: {
	item: { id: string; type: string; label: string; description?: string };
	index: number;
}) {
	return (
		<ComposerPrimitive.Unstable_TriggerPopoverItem
			item={item}
			index={index}
			className="flex w-full min-w-0 items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm outline-none data-[highlighted]:bg-accent hover:bg-accent/70 focus-visible:bg-accent"
		>
			<span className="min-w-0 flex-1 truncate font-medium">
				{item.label}
			</span>
			{item.description ? (
				<span className="text-muted-foreground max-w-[55%] truncate text-xs">
					{item.description}
				</span>
			) : null}
		</ComposerPrimitive.Unstable_TriggerPopoverItem>
	);
}

/**
 * Slash commands (`/`) and context mentions (`@`) for the Kolibri composer,
 * built on assistant-ui's unstable trigger-popover system. Commands transform
 * the composer input through the assistant-ui runtime; mentions insert
 * structured directives (`:context[...]{name=id}`) that the backend parses.
 */
export function KolibriComposerTriggers() {
	const aui = useAui();
	const slashCommands = useMemo<readonly Unstable_SlashCommand[]>(
		() =>
			SLASH_COMMANDS.map(({ id, label, description, prompt }) => ({
				id,
				label,
				description,
				execute: () => {
					aui.composer.setText(prompt);
				},
			})),
		[aui],
	);
	const slash = unstable_useSlashCommandAdapter({
		commands: slashCommands,
		removeOnExecute: true,
	});
	const mention = unstable_useMentionAdapter({
		categories: [
			{
				id: "context",
				label: "Контекст",
				items: [
					{
						id: "project",
						type: "context",
						label: "Проект",
						description: "Привязать ответ к проекту",
						icon: "FolderKanban",
					},
					{
						id: "estimate",
						type: "context",
						label: "Смета",
						description: "Работать с активной сметой",
						icon: "Calculator",
					},
					{
						id: "document",
						type: "context",
						label: "Документ",
						description: "Использовать документ как контекст",
						icon: "FileText",
					},
					{
						id: "file",
						type: "context",
						label: "Файл",
						description: "Указать файл из вложений",
						icon: "Paperclip",
					},
				],
			},
		],
		includeModelContextTools: {
			category: { id: "tools", label: "Инструменты" },
			formatLabel: (name) => name.replaceAll("_", " "),
		},
	});

	return (
		<>
			<ComposerPrimitive.Unstable_TriggerPopover
				adapter={slash.adapter}
				char="/"
				className={TRIGGER_POPOVER_CLASS}
			>
				<ComposerPrimitive.Unstable_TriggerPopover.Action
					{...slash.action}
				/>
				<ComposerPrimitive.Unstable_TriggerPopoverItems>
					{(items) =>
						items.map((item, index) => (
							<TriggerItemRow item={item} index={index} key={item.id} />
						))
					}
				</ComposerPrimitive.Unstable_TriggerPopoverItems>
			</ComposerPrimitive.Unstable_TriggerPopover>

			<ComposerPrimitive.Unstable_TriggerPopover
				adapter={mention.adapter}
				char="@"
				className={TRIGGER_POPOVER_CLASS}
			>
				<ComposerPrimitive.Unstable_TriggerPopover.Directive
					{...mention.directive}
				/>
				<ComposerPrimitive.Unstable_TriggerPopoverCategories>
					{(categories) =>
						categories.map((category) => (
							<ComposerPrimitive.Unstable_TriggerPopoverCategoryItem
								categoryId={category.id}
								key={category.id}
								className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm font-medium outline-none data-[highlighted]:bg-accent hover:bg-accent/70"
							>
								{category.label}
								<span className="text-muted-foreground text-xs">→</span>
							</ComposerPrimitive.Unstable_TriggerPopoverCategoryItem>
						))
					}
				</ComposerPrimitive.Unstable_TriggerPopoverCategories>
				<ComposerPrimitive.Unstable_TriggerPopoverBack className="flex w-full items-center gap-1 rounded-lg px-2.5 py-1.5 text-left text-xs text-muted-foreground outline-none hover:bg-accent/70">
					← Назад
				</ComposerPrimitive.Unstable_TriggerPopoverBack>
				<ComposerPrimitive.Unstable_TriggerPopoverItems>
					{(items) =>
						items.map((item, index) => (
							<TriggerItemRow item={item} index={index} key={item.id} />
						))
					}
				</ComposerPrimitive.Unstable_TriggerPopoverItems>
			</ComposerPrimitive.Unstable_TriggerPopover>
		</>
	);
}
