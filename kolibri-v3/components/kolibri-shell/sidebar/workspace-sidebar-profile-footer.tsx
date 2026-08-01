"use client";

import {
	Bird,
	Bot,
	LogOut,
	type LucideIcon,
	Settings,
	UserRound,
} from "lucide-react";
import { useState } from "react";
import { useSidebarPetState } from "@/components/kolibri-shell/sidebar/use-sidebar-state";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuShortcut,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { uiClassTokens } from "@/components/ui/class-names";
import { accountInitials } from "@/lib/identity/contracts";
import { useIdentity } from "@/lib/identity/provider";
import { cn } from "@/lib/utils";

type WorkspaceSidebarProfileFooterProps = {
	onOpenAiModels?: () => void;
	onOpenProfileSettings?: () => void;
};

type ProfileMenuItem = {
	icon: LucideIcon;
	label: string;
	onSelect: () => void | Promise<void>;
	shortcut?: string;
	disabled?: boolean;
};

const profileMenuItemClass = uiClassTokens.sidebarProfileMenuItem;

export function WorkspaceSidebarProfileFooter({
	onOpenAiModels,
	onOpenProfileSettings,
}: WorkspaceSidebarProfileFooterProps) {
	const identity = useIdentity();
	const { petVisible, togglePet } = useSidebarPetState(true);
	const [logoutPending, setLogoutPending] = useState(false);
	const [logoutError, setLogoutError] = useState<string | null>(null);

	const logout = async () => {
		setLogoutPending(true);
		setLogoutError(null);
		try {
			await identity.logout();
		} catch (error) {
			setLogoutError(
				error instanceof Error
					? error.message
					: "Не удалось выйти из аккаунта.",
			);
		} finally {
			setLogoutPending(false);
		}
	};

	const menuItems: ProfileMenuItem[] = [
		{
			icon: UserRound,
			label: "Личный кабинет",
			onSelect: () => onOpenProfileSettings?.(),
		},
		{
			icon: Bot,
			label: "Подключения моделей",
			onSelect: () => onOpenAiModels?.(),
			shortcut: "AI",
		},
		{
			icon: Bird,
			label: petVisible ? "Скрыть питомца" : "Показать питомца",
			onSelect: () => void togglePet(),
		},
		{
			icon: Settings,
			label: "Настройки",
			onSelect: () => onOpenProfileSettings?.(),
			shortcut: "⌘,",
		},
	];

	return (
		<div
			data-slot="workspace-profile-footer"
			className={cn(
				uiClassTokens.sidebarProfileFooter,
				"bg-[#f2f6ff] dark:bg-[#101721]",
			)}
		>
			<DropdownMenu>
				<DropdownMenuTrigger asChild>
					<button
						type="button"
						onClick={
							identity.status === "authenticated"
								? undefined
								: onOpenProfileSettings
						}
						data-slot="workspace-profile-trigger"
						className={cn(
							"focus-visible:ring-sidebar-ring/50",
							uiClassTokens.sidebarProfileTrigger,
						)}
						aria-label="Открыть меню личного кабинета"
					>
						<span
							data-slot="workspace-profile-avatar"
							aria-hidden="true"
							className={cn(
								uiClassTokens.sidebarProfileAvatar,
								"bg-[#fb927c]",
							)}
						>
							{accountInitials(identity.user)}
						</span>
						<span className="ml-2 flex min-w-0 flex-1 flex-col">
							<span className={uiClassTokens.sidebarProfileName}>
								{identity.user?.name ??
									(identity.status === "loading"
										? "Загрузка профиля"
										: "Войти в Kolibri")}
							</span>
							<span className={uiClassTokens.sidebarProfileMeta}>
								{identity.user
									? identity.user.role === "owner"
										? "Суперадминистратор"
										: "Пользователь"
									: identity.status === "offline"
										? "Нет связи"
										: "Личный кабинет"}
							</span>
						</span>
						<Settings
							aria-hidden="true"
							className="text-muted-foreground size-4 shrink-0"
						/>
					</button>
				</DropdownMenuTrigger>
				{identity.status === "authenticated" && identity.user ? (
					<DropdownMenuContent
						side="top"
						align="start"
						sideOffset={8}
						collisionPadding={8}
						className={uiClassTokens.sidebarProfileMenu}
					>
						<DropdownMenuLabel className={uiClassTokens.sidebarProfileMenuLabel}>
							<span className={uiClassTokens.sidebarProfileMenuLabelInline}>
								<span
									aria-hidden="true"
									className={cn(
										uiClassTokens.sidebarProfileAvatar,
										"size-8 text-[11px]",
									)}
								>
									{accountInitials(identity.user)}
								</span>
								<span className="min-w-0">
									<span className={uiClassTokens.sidebarProfileMenuName}>
										{identity.user.name}
									</span>
									<span className={uiClassTokens.sidebarProfileMenuEmail}>
										{identity.user.email}
									</span>
								</span>
							</span>
						</DropdownMenuLabel>
						<DropdownMenuSeparator />
						{menuItems.map((item) => (
							<DropdownMenuItem
								key={item.label}
								className={profileMenuItemClass}
								onSelect={item.onSelect}
								disabled={item.disabled}
							>
								<item.icon className="size-4" />
								{item.label}
								{item.shortcut ? (
									<DropdownMenuShortcut>{item.shortcut}</DropdownMenuShortcut>
								) : null}
							</DropdownMenuItem>
						))}
						<DropdownMenuSeparator />
						<DropdownMenuItem
							disabled={logoutPending}
							className={profileMenuItemClass}
							onSelect={() => void logout()}
						>
							<LogOut className="size-4" />
							{logoutPending ? "Выходим…" : "Выйти"}
						</DropdownMenuItem>
						{logoutError ? (
							<p
								role="alert"
								className="px-2.5 py-1.5 text-xs text-destructive"
							>
								{logoutError}
							</p>
						) : null}
					</DropdownMenuContent>
				) : null}
			</DropdownMenu>
		</div>
	);
}
