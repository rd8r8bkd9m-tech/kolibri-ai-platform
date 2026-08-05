"use client";

import { ThreadListPrimitive, useAui, useAuiState } from "@assistant-ui/react";
import {
	Bell,
	Blocks,
	ChevronDown,
	CircleHelp,
	Clock,
	Folder,
	GitPullRequest,
	Search,
	Settings,
	SquarePen,
} from "lucide-react";
import type { FC, ReactNode } from "react";

import { useIdentity } from "@/lib/identity/provider";

const rowClass =
	"flex h-8 w-full items-center gap-2 rounded-lg px-2 text-left text-[13px] font-medium text-(--color-text-foreground) hover:bg-black/[.05] focus-visible:outline-2 focus-visible:outline-(--color-ring)";

const iconClass = "size-4 shrink-0 text-(--color-icon-secondary)";

function SectionLabel({ children }: { children: ReactNode }) {
	return (
		<div className="px-2 pt-4 pb-1 text-[12px] font-medium text-(--color-text-foreground-tertiary)">
			{children}
		</div>
	);
}

const CodexThreadRow: FC = () => {
	const aui = useAui();
	const title = useAuiState(
		(state) => state.threadListItem.title || "Новый чат",
	);
	const isCurrent = useAuiState(
		(state) => state.threadListItem.id === state.threads.mainThreadId,
	);
	return (
		<button
			type="button"
			onClick={() => aui.threadListItem.switchTo()}
			className={`${rowClass} ${isCurrent ? "bg-black/[.07]" : ""}`}
		>
			<span className="min-w-0 flex-1 truncate text-left font-normal text-(--color-text-foreground-secondary)">
				{title}
			</span>
		</button>
	);
};

export const CodexSidebar: FC<{
	onOpenSettings?: (section?: "general" | "profile") => void;
}> = ({ onOpenSettings }) => {
	const identity = useIdentity();
	return (
		<aside className="flex h-full w-[248px] shrink-0 flex-col border-r border-(--color-border) bg-(--gray-75)">
			<header className="flex items-center justify-between px-4 pt-4 pb-2">
				<button
					type="button"
					className="flex items-center gap-1 rounded-md px-1 py-0.5 text-[15px] font-semibold hover:bg-black/[.05]"
				>
					Codex
					<ChevronDown className="size-3.5 text-(--color-icon-secondary)" />
				</button>
				<div className="flex items-center gap-1">
					<button type="button" className="rounded-md p-1.5 hover:bg-black/[.05]">
						<Search className={iconClass} />
					</button>
					<button type="button" className="relative rounded-md p-1.5 hover:bg-black/[.05]">
						<Bell className={iconClass} />
					</button>
				</div>
			</header>

			<nav className="flex flex-col gap-0.5 px-2">
				<ThreadListPrimitive.New asChild>
					<button type="button" className={rowClass}>
						<SquarePen className={iconClass} />
						Новый чат
					</button>
				</ThreadListPrimitive.New>
				<button type="button" className={rowClass}>
					<GitPullRequest className={iconClass} />
					Пулл-реквесты
				</button>
				<button type="button" className={rowClass}>
					<Clock className={iconClass} />
					<span className="flex-1 text-left">Запланировано</span>
					<span className="size-1.5 rounded-full bg-(--blue-400)" />
				</button>
				<button type="button" className={rowClass}>
					<Blocks className={iconClass} />
					Плагины
				</button>
			</nav>

			<div className="mt-2 flex-1 overflow-y-auto px-2 pb-2">
				<SectionLabel>Закреплённые</SectionLabel>
				<ThreadListPrimitive.Root>
					<ThreadListPrimitive.Items>
						{({ threadListItem }) => (
							<div key={threadListItem.id} className="flex flex-col gap-0.5">
								<CodexThreadRow />
							</div>
						)}
					</ThreadListPrimitive.Items>
				</ThreadListPrimitive.Root>
				<SectionLabel>Проекты</SectionLabel>
				<div className={rowClass}>
					<Folder className={iconClass} />
					kolibri-ai-platform
				</div>
			</div>

			<footer className="flex items-center justify-between border-t border-(--color-border) px-3 py-2.5">
				<button
					type="button"
					onClick={() => onOpenSettings?.(identity.user ? "profile" : "general")}
					className="flex min-w-0 items-center gap-2 rounded-md px-1.5 py-1 text-[13px] font-medium hover:bg-black/[.05]"
				>
					<Settings className={iconClass} />
					<span className="truncate">
						{identity.user?.email ?? "Войти в профиль"}
					</span>
				</button>
				<button
					type="button"
					onClick={() => onOpenSettings?.("general")}
					className="rounded-md p-1.5 hover:bg-black/[.05]"
				>
					<CircleHelp className={iconClass} />
				</button>
			</footer>
		</aside>
	);
};
