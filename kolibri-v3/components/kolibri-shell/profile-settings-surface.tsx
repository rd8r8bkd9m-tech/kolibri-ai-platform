"use client";

import {
	Bird,
	Bot,
	Check,
	Code2,
	CreditCard,
	KeyRound,
	LoaderCircle,
	LogIn,
	LogOut,
	type LucideIcon,
	Monitor,
	Moon,
	Palette,
	Plug,
	Plus,
	RefreshCw,
	Search,
	Settings2,
	ShieldCheck,
	Store,
	Sun,
	TestTube2,
	Trash2,
	UserRound,
} from "lucide-react";
import {
	type FormEvent,
	type KeyboardEvent,
	type ReactNode,
	useCallback,
	useEffect,
	useId,
	useMemo,
	useRef,
	useState,
} from "react";
import { AgentProfileSelector } from "@/components/assistant-ui/agent-profile-selector";
import { BillingAccountSection } from "@/components/billing/billing-account-section";
import { PlatformAdminSection } from "@/components/kolibri-shell/platform-admin-section";
import {
	KOLIBRI_PET_SELECTION_EVENT,
	KOLIBRI_PET_VISIBILITY_EVENT,
	KOLIBRI_PET_VISIBILITY_KEY,
	KOLIBRI_PETS,
	type KolibriPetId,
	PetAvatar,
	readKolibriPetId,
	readKolibriPetVisibility,
	setKolibriPetId,
	setKolibriPetVisibility,
} from "@/components/kolibri-shell/kolibri-pet";
import {
	type KolibriThemePreference,
	useKolibriTheme,
} from "@/components/theme/kolibri-theme-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type AgentProfile, accountInitials } from "@/lib/identity/contracts";
import { useIdentity } from "@/lib/identity/provider";
import { useModelCatalog } from "@/lib/models/provider";
import { effectiveModelSelectionId } from "@/lib/models/selection";
import {
	createUserModel,
	deleteUserModel,
	getUserModels,
	testUserModel,
	updateUserModel,
	type UserManagedModel,
	type UserModelCreate,
} from "@/lib/models/user-models-client";
import {
	connectCodexLogin,
	connectMimo,
	createProviderEnrollmentNonce,
	getProviders,
	LOCAL_PROVIDER_CONNECTIONS_ENABLED,
	type ProviderId,
	type ProviderList,
	type ProviderProjection,
	startProviderEnrollment,
} from "@/lib/providers/client";
import { cn } from "@/lib/utils";

export type ProfileSettingsSection =
	| "general"
	| "profile"
	| "appearance"
	| "pet"
	| "ai-models"
	| "security"
	| "billing"
	| "platform-admin"
	| "marketplaces"
	| "integrations";

export type ProfileSettingsSurfaceProps = {
	activeSection?: ProfileSettingsSection;
	onSectionChange?: (section: ProfileSettingsSection) => void;
	initialSection?: ProfileSettingsSection;
};

const SECTION_GROUPS: readonly {
	label: string;
	sections: readonly {
		id: ProfileSettingsSection;
		label: string;
		icon: LucideIcon;
		keywords: string;
	}[];
}[] = [
	{
		label: "Персональные настройки",
		sections: [
			{
				id: "general",
				label: "Общее",
				icon: Settings2,
				keywords: "язык файлы рабочая область",
			},
			{
				id: "profile",
				label: "Профиль",
				icon: UserRound,
				keywords: "имя email аккаунт",
			},
			{
				id: "appearance",
				label: "Внешний вид",
				icon: Palette,
				keywords: "тема цвет интерфейс",
			},
			{
				id: "pet",
				label: "Питомец",
				icon: Bird,
				keywords: "kolibri показать скрыть",
			},
		],
	},
	{
		label: "ИИ и безопасность",
		sections: [
			{
				id: "ai-models",
				label: "Модели и подключения",
				icon: Bot,
				keywords: "mimo codex ключ api ии",
			},
			{
				id: "security",
				label: "Безопасность",
				icon: ShieldCheck,
				keywords: "сессия выход доступ",
			},
		],
	},
	{
		label: "Бизнес",
		sections: [
			{
				id: "billing",
				label: "Использование и оплата",
				icon: CreditCard,
				keywords: "лимит тариф токены платежи",
			},
			{
				id: "platform-admin",
				label: "Управление платформой",
				icon: ShieldCheck,
				keywords: "superadmin клиенты tenant пользователи роли лимиты аудит",
			},
			{
				id: "marketplaces",
				label: "Маркетплейсы",
				icon: Store,
				keywords: "площадки поставщики магазины",
			},
			{
				id: "integrations",
				label: "Интеграции",
				icon: Plug,
				keywords: "mcp подключение сервисы",
			},
		],
	},
];

export function profileSettingsSectionLabel(section: ProfileSettingsSection) {
	return (
		SECTION_GROUPS.flatMap((group) => group.sections).find(
			(candidate) => candidate.id === section,
		)?.label ?? "Настройки"
	);
}

const PROFILE_PRESENTATION: Record<
	AgentProfile,
	{ label: string; description: string }
> = {
	auto: {
		label: "Авто",
		description: "Kolibri выберет доступную модель для задачи.",
	},
	"mimo-code": {
		label: "MiMo 2.5 Pro",
		description: "Модель MiMo Code для повседневных запросов.",
	},
	"codex-cli": {
		label: "Codex",
		description: "Модель для сложных задач, анализа и кода.",
	},
};

export function ProfileSettingsSurface({
	activeSection: controlledSection,
	onSectionChange,
	initialSection = "general",
}: ProfileSettingsSurfaceProps) {
	const identity = useIdentity();
	const [internalSection, setInternalSection] =
		useState<ProfileSettingsSection>(initialSection);
	const activeSection = controlledSection ?? internalSection;
	const [search, setSearch] = useState("");
	const selectSection = (section: ProfileSettingsSection) => {
		setInternalSection(section);
		onSectionChange?.(section);
	};

	useEffect(() => {
		if (controlledSection === undefined) {
			setInternalSection(initialSection);
		}
	}, [controlledSection, initialSection]);

	const roleLabel = identity.user?.isPlatformOwner
		? "Суперадминистратор"
		: "Пользователь";
	const normalizedSearch = search.trim().toLowerCase();
	const filteredGroups = useMemo(
		() =>
			SECTION_GROUPS.map((group) => ({
				...group,
				sections: group.sections.filter(
					(section) =>
						(section.id !== "platform-admin" ||
							identity.user?.isPlatformOwner === true) &&
						(!normalizedSearch ||
							section.label.toLowerCase().includes(normalizedSearch) ||
							section.keywords.includes(normalizedSearch)),
				),
			})).filter((group) => group.sections.length > 0),
		[identity.user?.isPlatformOwner, normalizedSearch],
	);
	const activeSectionLabel = profileSettingsSectionLabel(activeSection);

	return (
		<section
			data-slot="settings-canvas-surface"
			aria-label="Настройки Kolibri"
			className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background"
		>
			{identity.status === "loading" ? (
				<LoadingAccount />
			) : identity.status !== "authenticated" || !identity.user ? (
				<AuthPanel onAuthenticated={() => undefined} />
			) : (
				<div
					data-slot="settings-canvas-layout"
					className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] @min-[760px]:grid-cols-[230px_minmax(0,1fr)] @min-[760px]:grid-rows-1"
				>
					<aside
						aria-label="Разделы настроек"
						data-slot="settings-canvas-navigation"
						className="hidden h-full min-h-0 flex-col border-r border-border bg-sidebar dark:border-border dark:bg-sidebar @min-[760px]:flex"
					>
						<div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
							<div className="relative">
							<Search
								aria-hidden="true"
								className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
							/>
							<Input
								type="search"
								value={search}
								onChange={(event) => setSearch(event.target.value)}
								placeholder="Поиск настроек…"
								aria-label="Поиск настроек"
								className="h-9 rounded-lg border-border/70 bg-background/80 pl-9 text-[12px] shadow-none dark:border-white/10 dark:bg-white/[0.06]"
							/>
							</div>
							<nav className="mt-4" aria-label="Все настройки">
							{filteredGroups.length ? (
								filteredGroups.map((group) => (
									<div
										key={group.label}
										data-slot="account-settings-group"
										className="mb-4"
									>
										<h2 className="text-muted-foreground mb-1 px-2 text-[10px] font-medium uppercase tracking-wide">
											{group.label}
										</h2>
										<ul className="space-y-0.5">
											{group.sections.map(({ id, icon: Icon, label }) => (
												<li key={id}>
													<button
														type="button"
														aria-current={
															activeSection === id ? "page" : undefined
														}
													onClick={() => selectSection(id)}
													className={cn(
														"flex min-h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-left text-[13px] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[color-mix(in_oklab,var(--brand)_50%,transparent)]",
														activeSection === id
															? "bg-[var(--brand-soft-strong)] text-foreground dark:bg-[var(--brand-soft-strong)]"
															: "hover:bg-[var(--brand-soft)] dark:hover:bg-[var(--brand-soft)]",
													)}
													>
														<Icon
															className="size-4 shrink-0"
															aria-hidden="true"
														/>
														<span className="truncate">{label}</span>
													</button>
												</li>
											))}
										</ul>
									</div>
								))
							) : (
								<p className="text-muted-foreground px-2 py-4 text-sm">
									Настройки не найдены
								</p>
							)}
							</nav>
						</div>
						<div className="flex shrink-0 items-center gap-2 border-t border-border px-3 py-3">
							<span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#fb927c] text-[11px] font-medium text-white">
								{accountInitials(identity.user)}
							</span>
							<span className="min-w-0">
								<span className="block truncate text-[12px] font-semibold">
									{identity.user.name}
								</span>
								<span className="text-muted-foreground block truncate text-[10px]">
									{roleLabel}
								</span>
							</span>
						</div>
					</aside>

					<header
						data-slot="settings-canvas-mobile-navigation"
						className="min-w-0 border-b bg-background px-3 py-3 @min-[760px]:hidden"
					>
						<div className="flex items-center justify-between gap-3">
							<div className="min-w-0">
								<p className="text-[13px] font-semibold">Настройки</p>
								<p className="text-muted-foreground truncate text-[10px]">
									{activeSectionLabel}
								</p>
							</div>
							<span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#fb927c] text-[11px] font-medium text-white">
								{accountInitials(identity.user)}
							</span>
						</div>
						<nav
							aria-label="Разделы настроек"
							className="mt-3 flex gap-1 overflow-x-auto overscroll-x-contain pb-0.5"
						>
							{filteredGroups
								.flatMap((group) => group.sections)
								.map(({ id, icon: Icon, label }) => (
									<button
										type="button"
										key={id}
										aria-current={activeSection === id ? "page" : undefined}
										onClick={() => selectSection(id)}
										className={cn(
											"flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-[11px] font-medium",
											activeSection === id
												? "bg-[var(--brand-soft-strong)] text-foreground dark:text-foreground"
												: "text-muted-foreground hover:bg-[var(--brand-soft)] hover:text-foreground",
										)}
									>
										<Icon className="size-3.5" aria-hidden="true" />
										{label}
									</button>
								))}
						</nav>
					</header>

					<main
						data-slot="settings-canvas-content"
						className="min-h-0 overflow-y-auto overscroll-contain bg-background px-4 py-5 @min-[760px]:px-8 @min-[760px]:py-7"
					>
						<div
							className={cn(
								"mx-auto w-full",
								activeSection === "platform-admin"
									? "max-w-[1320px]"
									: "max-w-[860px]",
							)}
						>
							<SettingsSectionContent section={activeSection} />
						</div>
					</main>
				</div>
			)}
		</section>
	);
}

function SettingsSectionContent({
	section,
}: {
	section: ProfileSettingsSection;
}) {
	const identity = useIdentity();
	if (section === "general") return <GeneralSection />;
	if (section === "profile") return <ProfileSection />;
	if (section === "appearance") return <AppearanceSection />;
	if (section === "pet") return <PetSettingsSection />;
	if (section === "ai-models") return <AiModelsSection />;
	if (section === "security") return <SecuritySection />;
	if (section === "billing") return <BillingAccountSection />;
	if (section === "platform-admin") {
		return identity.user?.isPlatformOwner ? (
			<PlatformAdminSection />
		) : (
			<EmptyProductSection
				icon={ShieldCheck}
				title="Управление платформой"
				description="Этот раздел доступен только владельцу платформы."
				empty="Недостаточно прав для просмотра."
			/>
		);
	}
	if (section === "marketplaces") {
		return (
			<EmptyProductSection
				icon={Store}
				title="Маркетплейсы"
				description="Управление площадками и предложениями поставщиков."
				empty="Подключённых маркетплейсов пока нет."
			/>
		);
	}
	return (
		<EmptyProductSection
			icon={Plug}
			title="Интеграции"
			description="Внешние сервисы и MCP-подключения Kolibri."
			empty="Подключённых внешних сервисов пока нет."
		/>
	);
}

function LoadingAccount() {
	return (
		<div
			className="flex min-h-0 flex-1 items-center justify-center gap-2 text-sm text-muted-foreground"
			role="status"
		>
			<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
			Загружаем защищённую сессию
		</div>
	);
}

function AuthPanel({ onAuthenticated }: { onAuthenticated: () => void }) {
	const identity = useIdentity();
	const [mode, setMode] = useState<"login" | "register">("login");
	const [name, setName] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(identity.error);
	const authTabPrefix = useId().replace(/:/g, "");
	const authTabRefs = useRef<Array<HTMLButtonElement | null>>([]);

	const loginTabId = `${authTabPrefix}-account-login-tab`;
	const registerTabId = `${authTabPrefix}-account-register-tab`;
	const loginPanelId = `${authTabPrefix}-account-auth-login-panel`;
	const registerPanelId = `${authTabPrefix}-account-auth-register-panel`;

	const switchMode = (nextMode: "login" | "register") => {
		setMode(nextMode);
		setError(null);
	};

	const focusModeTab = (nextMode: "login" | "register", nextIndex: number) => {
		switchMode(nextMode);
		window.requestAnimationFrame(() => {
			authTabRefs.current[nextIndex]?.focus();
		});
	};

	const handleModeKeyDown = (
		event: KeyboardEvent<HTMLButtonElement>,
		index: number,
	) => {
		let nextIndex: number | null = null;
		if (event.key === "ArrowRight") {
			nextIndex = (index + 1) % 2;
		} else if (event.key === "ArrowLeft") {
			nextIndex = (index - 1 + 2) % 2;
		} else if (event.key === "Home") {
			nextIndex = 0;
		} else if (event.key === "End") {
			nextIndex = 1;
		}

		if (nextIndex === null) {
			return;
		}

		event.preventDefault();
		const nextMode = nextIndex === 0 ? "login" : "register";
		focusModeTab(nextMode, nextIndex);
	};

	const submit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setSubmitting(true);
		setError(null);
		try {
			if (mode === "login") {
				await identity.login({ email, password });
			} else {
				await identity.register({ email, name, password });
			}
			setPassword("");
			onAuthenticated();
		} catch (requestError) {
			setError(
				requestError instanceof Error
					? requestError.message
					: "Не удалось подтвердить аккаунт.",
			);
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<div className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:px-8">
			<div className="mx-auto w-full max-w-sm">
				<div
					role="tablist"
					aria-label="Способ входа"
					aria-orientation="horizontal"
					className="grid grid-cols-2 rounded-xl bg-muted p-1"
				>
					<button
						type="button"
						role="tab"
						ref={(node) => {
							authTabRefs.current[0] = node;
						}}
						id={loginTabId}
						aria-controls={loginPanelId}
						aria-selected={mode === "login"}
						tabIndex={mode === "login" ? 0 : -1}
						onClick={() => switchMode("login")}
						onKeyDown={(event) => handleModeKeyDown(event, 0)}
						className={cn(
							"h-9 rounded-lg text-sm font-medium",
							mode === "login"
								? "bg-background shadow-sm"
								: "text-muted-foreground",
						)}
					>
						Вход
					</button>
					<button
						type="button"
						role="tab"
						ref={(node) => {
							authTabRefs.current[1] = node;
						}}
						id={registerTabId}
						aria-controls={registerPanelId}
						aria-selected={mode === "register"}
						tabIndex={mode === "register" ? 0 : -1}
						onClick={() => switchMode("register")}
						onKeyDown={(event) => handleModeKeyDown(event, 1)}
						className={cn(
							"h-9 rounded-lg text-sm font-medium",
							mode === "register"
								? "bg-background shadow-sm"
								: "text-muted-foreground",
						)}
					>
						Регистрация
					</button>
				</div>

				{mode === "login" ? (
					<form
						id={loginPanelId}
						role="tabpanel"
						aria-labelledby={loginTabId}
						tabIndex={0}
						className="mt-5 space-y-4"
						onSubmit={submit}
					>
						<h2 className="sr-only">Вход</h2>
						<label className="block text-[13px] font-medium">
							Email
							<Input
								type="email"
								value={email}
								onChange={(event) => setEmail(event.target.value)}
								autoComplete="email"
								required
								maxLength={320}
								className="mt-2 h-10 rounded-lg shadow-none"
							/>
						</label>
						<label className="block text-[13px] font-medium">
							Пароль
							<Input
								type="password"
								value={password}
								onChange={(event) => setPassword(event.target.value)}
								autoComplete="current-password"
								required
								minLength={12}
								maxLength={256}
								className="mt-2 h-10 rounded-lg shadow-none"
							/>
						</label>
						{error ? (
							<p
								className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] leading-5 text-destructive"
								role="alert"
							>
								{error}
							</p>
						) : null}
						<Button
							type="submit"
							disabled={submitting}
							className="h-10 w-full rounded-lg"
						>
							{submitting ? (
								<LoaderCircle
									className="size-4 animate-spin"
									aria-hidden="true"
								/>
							) : null}
							Войти
						</Button>
					</form>
				) : (
					<form
						id={registerPanelId}
						role="tabpanel"
						aria-labelledby={registerTabId}
						tabIndex={0}
						className="mt-5 space-y-4"
						onSubmit={submit}
					>
						<h2 className="sr-only">Регистрация</h2>
						<label className="block text-[13px] font-medium">
							Имя
							<Input
								value={name}
								onChange={(event) => setName(event.target.value)}
								autoComplete="name"
								required
								minLength={2}
								maxLength={160}
								className="mt-2 h-10 rounded-lg shadow-none"
							/>
						</label>
						<label className="block text-[13px] font-medium">
							Email
							<Input
								type="email"
								value={email}
								onChange={(event) => setEmail(event.target.value)}
								autoComplete="email"
								required
								maxLength={320}
								className="mt-2 h-10 rounded-lg shadow-none"
							/>
						</label>
						<label className="block text-[13px] font-medium">
							Пароль
							<Input
								type="password"
								value={password}
								onChange={(event) => setPassword(event.target.value)}
								autoComplete="new-password"
								required
								minLength={12}
								maxLength={256}
								className="mt-2 h-10 rounded-lg shadow-none"
							/>
						</label>
						{error ? (
							<p
								className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] leading-5 text-destructive"
								role="alert"
							>
								{error}
							</p>
						) : null}
						<Button
							type="submit"
							disabled={submitting}
							className="h-10 w-full rounded-lg"
						>
							{submitting ? (
								<LoaderCircle
									className="size-4 animate-spin"
									aria-hidden="true"
								/>
							) : null}
							Создать аккаунт
						</Button>
					</form>
				)}

			</div>
		</div>
	);
}

function GeneralSection() {
	const identity = useIdentity();
	const modelCatalog = useModelCatalog();
	const effectiveModelId = identity.user
		? effectiveModelSelectionId(
				modelCatalog.catalog?.models ?? [],
				identity.user,
			)
		: undefined;
	const selectedModel = identity.user
		? (modelCatalog.catalog?.models.find(
				(model) => `${model.profile}:${model.id}` === effectiveModelId,
			)?.displayName ??
			PROFILE_PRESENTATION[identity.user.preferredAgentProfile].label)
		: "Авто";

	return (
		<section>
			<SectionHeading
				icon={Settings2}
				title="Общее"
				description="Основное поведение рабочего пространства Kolibri."
			/>

			<SettingsGroup title="Рабочая область">
				<SettingsRow
					title="Открывать документы"
					description="Проекты, сметы и файлы открываются в едином мультимодальном холсте."
					value="В холсте"
				/>
				<SettingsRow
					title="Язык интерфейса"
					description="Язык меню, подсказок и системных сообщений."
					value="Русский"
				/>
				<SettingsRow
					title="Модель по умолчанию"
					description="Выбранный режим применяется к новым сообщениям."
					value={selectedModel}
				/>
			</SettingsGroup>

			<SettingsGroup title="Сохранение">
				<SettingsRow
					title="Автосохранение"
					description="Чаты и изменения документов сохраняются в пространстве пользователя."
					value="Включено"
				/>
			</SettingsGroup>
		</section>
	);
}

function AppearanceSection() {
	const { preference, resolvedTheme, setPreference } = useKolibriTheme();
	const themes: readonly {
		description: string;
		icon: LucideIcon;
		label: string;
		value: KolibriThemePreference;
	}[] = [
		{
			description: `Сейчас используется ${resolvedTheme === "dark" ? "тёмная" : "светлая"}`,
			icon: Monitor,
			label: "Системная",
			value: "system",
		},
		{
			description: "Светлый фон и тёмный текст",
			icon: Sun,
			label: "Светлая",
			value: "light",
		},
		{
			description: "Чёрный фон и светлый текст",
			icon: Moon,
			label: "Тёмная",
			value: "dark",
		},
	];

	return (
		<section>
			<SectionHeading
				icon={Palette}
				title="Внешний вид"
				description="Спокойная рабочая среда без визуального шума."
			/>

			<SettingsGroup title="Интерфейс">
				<div
					data-slot="appearance-options"
					className="grid gap-2 px-4 py-4 min-[960px]:grid-cols-3"
				>
					{themes.map(({ description, icon: Icon, label, value }) => {
						const selected = preference === value;
						return (
							<button
								key={value}
								data-slot="appearance-option"
								type="button"
								aria-pressed={selected}
								onClick={() => setPreference(value)}
								className={cn(
									"flex min-h-24 flex-col items-start rounded-2xl border bg-background p-3 text-left outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
									selected && "border-sky-500 bg-sky-50 dark:bg-sky-950/35",
								)}
							>
								<span
									data-slot="appearance-option-header"
									className="flex w-full items-center justify-between"
								>
									<Icon aria-hidden="true" className="size-5" />
									<span
										data-slot="appearance-option-mobile-label"
										className="hidden min-w-0 flex-1 truncate px-3 text-base font-semibold max-[959px]:inline"
									>
										{label}
									</span>
									{selected ? (
										<Check
											aria-hidden="true"
											className="size-4 text-sky-600 dark:text-sky-300"
										/>
									) : null}
								</span>
								<span
									data-slot="appearance-option-desktop-label"
									className="mt-3 text-[13px] font-semibold max-[959px]:hidden"
								>
									{label}
								</span>
								<span
									data-slot="appearance-option-description"
									className="text-muted-foreground mt-1 text-[10px] leading-4"
								>
									{description}
								</span>
							</button>
						);
					})}
				</div>
				<SettingsRow
					title="Боковая панель"
					description="Мягкий голубой фон отделяет навигацию от рабочего холста."
					value="Голубая"
				/>
				<SettingsRow
					title="Плотность"
					description="Компактные строки сохраняют больше места для документов и чата."
					value="Компактная"
				/>
			</SettingsGroup>
		</section>
	);
}

function PetSettingsSection() {
	const [selectedPet, setSelectedPet] = useState<KolibriPetId>("kolibri");
	const [visible, setVisible] = useState(true);

	useEffect(() => {
		setSelectedPet(readKolibriPetId());
		setVisible(readKolibriPetVisibility());

		const syncVisibility = (event: Event) => {
			const next = (event as CustomEvent<{ visible?: unknown }>).detail
				?.visible;
			if (typeof next === "boolean") setVisible(next);
		};
		const syncSelection = (event: Event) => {
			const next = (event as CustomEvent<{ id?: unknown }>).detail?.id;
			if (KOLIBRI_PETS.some((pet) => pet.id === next)) {
				setSelectedPet(next as KolibriPetId);
			}
		};

		globalThis.addEventListener(KOLIBRI_PET_VISIBILITY_EVENT, syncVisibility);
		globalThis.addEventListener(KOLIBRI_PET_SELECTION_EVENT, syncSelection);
		return () => {
			globalThis.removeEventListener(
				KOLIBRI_PET_VISIBILITY_EVENT,
				syncVisibility,
			);
			globalThis.removeEventListener(
				KOLIBRI_PET_SELECTION_EVENT,
				syncSelection,
			);
		};
	}, []);

	const toggleVisibility = () => {
		const next = !visible;
		setVisible(next);
		setKolibriPetVisibility(next);
	};

	const selectPet = (id: KolibriPetId) => {
		setSelectedPet(id);
		setKolibriPetId(id);
		if (!visible) {
			setVisible(true);
			setKolibriPetVisibility(true);
		}
	};

	return (
		<section>
			<SectionHeading
				icon={Bird}
				title="Питомцы"
				description="Выберите одного из друзей Kolibri — у каждого свой характер и реакция."
			/>

			<SettingsGroup title="Отображение">
				<div className="flex items-center justify-between gap-5 px-5 py-4">
					<div>
						<p className="text-[14px] font-medium">Показывать питомца</p>
						<p className="text-muted-foreground mt-1 text-[12px] leading-5">
							Питомца можно двигать по всему экрану, нажимать на него и убирать
							к ближайшему краю.
						</p>
					</div>
					<SettingsSwitch
						checked={visible}
						label="Показывать питомца в боковой панели"
						onChange={toggleVisibility}
					/>
				</div>
			</SettingsGroup>

			<div className="mt-8">
				<div className="mb-3">
					<h3 className="text-[15px] font-semibold">Выберите питомца</h3>
					<p className="text-muted-foreground mt-1 text-[12px]">
						Десять оригинальных персонажей. Никаких закрытых или платных
						питомцев.
					</p>
				</div>
				<div
					aria-label="Каталог питомцев"
					className="grid grid-cols-1 gap-2 min-[540px]:grid-cols-2"
					role="group"
				>
					{KOLIBRI_PETS.map((pet) => {
						const selected = pet.id === selectedPet;
						return (
							<button
								aria-label={`Выбрать питомца ${pet.name}. Роль: ${pet.role}. Характер: ${pet.personality}. ${pet.description} Реакция: ${pet.animation}.`}
								aria-pressed={selected}
								data-pet-option={pet.id}
								key={pet.id}
								onClick={() => selectPet(pet.id)}
								type="button"
								className={cn(
									"group relative flex min-h-[112px] items-center gap-3 rounded-2xl border bg-card px-3 py-3 text-left outline-none transition-[border-color,background-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-sky-300/80 hover:bg-sky-50/45 focus-visible:ring-2 focus-visible:ring-sky-400/60 dark:hover:border-sky-800 dark:hover:bg-sky-950/25",
									selected &&
										"border-sky-300 bg-sky-50/70 shadow-[0_8px_24px_rgb(14_165_233_/_0.08)] dark:border-sky-800 dark:bg-sky-950/35",
								)}
							>
								<PetAvatar
									id={pet.id}
									active={selected}
									className="size-16 rounded-2xl bg-[color-mix(in_srgb,var(--card)_82%,transparent)]"
								/>
								<div className="min-w-0 flex-1">
									<div className="flex items-baseline gap-2">
										<p className="truncate text-[14px] font-semibold">
											{pet.name}
										</p>
										<span className="text-muted-foreground shrink-0 text-[10px] font-medium uppercase tracking-[0.08em]">
											{pet.role}
										</span>
									</div>
									<p className="text-foreground/70 mt-0.5 truncate text-[11px] font-medium">
										{pet.personality}
									</p>
									<p className="text-muted-foreground mt-1 line-clamp-2 text-[11px] leading-4">
										{pet.description}
									</p>
									<p className="mt-1.5 text-[10px] font-medium text-sky-700 dark:text-sky-300">
										Реакция: {pet.animation}
									</p>
								</div>
								<span
									aria-hidden="true"
									className={cn(
										"absolute top-2 right-2 grid size-5 place-items-center rounded-full border bg-background/90 text-transparent transition",
										selected &&
											"border-sky-400 bg-sky-500 text-white dark:border-sky-500",
									)}
								>
									<Check className="size-4" />
								</span>
							</button>
						);
					})}
				</div>
			</div>
		</section>
	);
}

function EmptyProductSection({
	description,
	empty,
	icon: Icon,
	title,
}: {
	description: string;
	empty: string;
	icon: LucideIcon;
	title: string;
}) {
	return (
		<section>
			<SectionHeading icon={Icon} title={title} description={description} />
			<div className="mt-8 flex min-h-52 flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/15 px-6 text-center">
				<span className="flex size-11 items-center justify-center rounded-2xl bg-muted">
					<Icon className="text-muted-foreground size-5" aria-hidden="true" />
				</span>
				<p className="mt-4 max-w-md text-sm font-medium">{empty}</p>
				<p className="text-muted-foreground mt-1 max-w-md text-[12px] leading-5">
					Раздел уже находится на своём постоянном месте и будет заполняться
					только реальными данными.
				</p>
			</div>
		</section>
	);
}

function SettingsGroup({
	children,
	title,
}: {
	children: ReactNode;
	title: string;
}) {
	return (
		<section data-slot="settings-content-group" className="mt-8">
			<h3 className="mb-3 text-[15px] font-semibold">{title}</h3>
			<div className="divide-y overflow-hidden rounded-2xl border bg-card">
				{children}
			</div>
		</section>
	);
}

function SettingsRow({
	description,
	title,
	value,
}: {
	description: string;
	title: string;
	value: string;
}) {
	return (
		<div
			data-slot="settings-content-row"
			className="flex items-center justify-between gap-5 px-5 py-4"
		>
			<div data-slot="settings-content-copy" className="min-w-0">
				<p
					data-slot="settings-content-title"
					className="text-[14px] font-medium"
				>
					{title}
				</p>
				<p
					data-slot="settings-content-description"
					className="text-muted-foreground mt-1 text-[12px] leading-5"
				>
					{description}
				</p>
			</div>
			<span
				data-slot="settings-content-value"
				className="bg-muted/70 text-muted-foreground shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] font-medium"
			>
				{value}
			</span>
		</div>
	);
}

function SettingsSwitch({
	checked,
	label,
	onChange,
}: {
	checked: boolean;
	label: string;
	onChange: () => void;
}) {
	return (
		<button
			type="button"
			role="switch"
			aria-checked={checked}
			aria-label={label}
			onClick={onChange}
			className={cn(
				"relative h-6 w-11 shrink-0 rounded-full outline-none transition-colors focus-visible:ring-2 focus-visible:ring-sky-400/60 focus-visible:ring-offset-2",
				checked ? "bg-sky-500" : "bg-muted-foreground/30",
			)}
		>
			<span
				className={cn(
					"absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow-sm transition-transform",
					checked && "translate-x-5",
				)}
			/>
		</button>
	);
}

function ProfileSection() {
	const identity = useIdentity();
	const user = identity.user!;
	const [name, setName] = useState(user.name);
	const [saving, setSaving] = useState(false);
	const [message, setMessage] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);

	useEffect(() => {
		setName(user.name);
	}, [user.name]);

	const submit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setSaving(true);
		setMessage(null);
		setFailed(false);
		try {
			await identity.saveProfile({ name });
			setMessage("Профиль сохранён.");
		} catch (error) {
			setFailed(true);
			setMessage(
				error instanceof Error ? error.message : "Профиль не сохранён.",
			);
		} finally {
			setSaving(false);
		}
	};

	return (
		<section>
			<SectionHeading
				icon={UserRound}
				title="Личный профиль"
				description="Имя и данные аккаунта сохраняются в вашем пространстве Kolibri."
			/>

			<div className="mt-6 flex items-center gap-4 rounded-2xl border bg-card p-4">
				<div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#fb927c] text-[13px] font-semibold text-white">
					{accountInitials(user)}
				</div>
				<div className="min-w-0">
					<p className="truncate text-[14px] font-semibold">{user.name}</p>
					<p className="text-muted-foreground mt-0.5 truncate text-[13px]">
						{user.email}
					</p>
					<p className="text-muted-foreground mt-1 text-[12px]">
						{user.isPlatformOwner ? "Суперадминистратор" : "Пользователь"}
					</p>
				</div>
			</div>

			<form className="mt-6 space-y-5" onSubmit={submit}>
				<label className="block text-[13px] font-medium">
					Имя
					<Input
						value={name}
						onChange={(event) => setName(event.target.value)}
						autoComplete="name"
						minLength={2}
						maxLength={160}
						required
						className="mt-2 h-10 rounded-lg shadow-none"
					/>
				</label>
				<label className="block text-[13px] font-medium">
					Email для входа
					<Input
						type="email"
						value={user.email}
						autoComplete="email"
						readOnly
						aria-describedby="profile-email-note"
						className="mt-2 h-10 rounded-lg bg-muted/30 shadow-none"
					/>
					<span
						id="profile-email-note"
						className="text-muted-foreground mt-1.5 block text-[11px] font-normal"
					>
						Смена email будет доступна отдельным защищённым действием.
					</span>
				</label>
				<div className="flex flex-wrap items-center gap-3">
					<Button type="submit" disabled={saving} className="rounded-lg">
						{saving ? (
							<LoaderCircle
								className="size-4 animate-spin"
								aria-hidden="true"
							/>
						) : null}
						Сохранить
					</Button>
					{message ? (
						<span
							className={cn(
								"text-[12px]",
								failed ? "text-destructive" : "text-muted-foreground",
							)}
							role={failed ? "alert" : "status"}
						>
							{message}
						</span>
					) : null}
				</div>
			</form>
		</section>
	);
}

function AiModelsSection() {
	const identity = useIdentity();
	const modelCatalog = useModelCatalog();
	const user = identity.user!;
	const isSuperadmin = user.isPlatformOwner;
	const [providers, setProviders] = useState<ProviderList | null>(null);
	const [loading, setLoading] = useState(isSuperadmin);
	const [busy, setBusy] = useState<string | null>(null);
	const [message, setMessage] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);
	const [mimoKey, setMimoKey] = useState("");

	const load = useCallback(
		async (signal?: AbortSignal) => {
			if (!isSuperadmin) {
				setProviders(null);
				setLoading(false);
				return false;
			}

			setLoading(true);
			try {
				setProviders(await getProviders(signal));
				setFailed(false);
				setMessage(null);
				return true;
			} catch (error) {
				if (error instanceof DOMException && error.name === "AbortError") {
					return false;
				}
				setProviders(null);
				setFailed(true);
				setMessage(
					error instanceof Error
						? error.message
						: "Статус провайдеров недоступен.",
				);
				return false;
			} finally {
				if (!signal?.aborted) setLoading(false);
			}
		},
		[isSuperadmin],
	);

	useEffect(() => {
		if (!isSuperadmin) return;
		const controller = new AbortController();
		void load(controller.signal);
		return () => controller.abort();
	}, [isSuperadmin, load]);

	const providerById = (id: ProviderId) =>
		providers?.providers.find((provider) => provider.id === id);
	const mimoProvider = providerById("mimo-code");
	const codexProvider = providerById("codex-cli");
	const mimoConnected = mimoProvider?.status === "connected";
	const codexConnected = codexProvider?.status === "connected";

	const updateProviderProjection = (
		providerId: ProviderId,
		provider: ProviderProjection,
	) => {
		setProviders((current) =>
			current
				? {
						...current,
						providers: current.providers.map((candidate) =>
							candidate.id === providerId ? provider : candidate,
						),
					}
				: current,
		);
	};

	const connectLocalProvider = async (providerId: ProviderId) => {
		setBusy(`connect:${providerId}`);
		setFailed(false);
		setMessage(null);
		try {
			const enrollment =
				providerId === "mimo-code"
					? await connectMimo(mimoKey)
					: await connectCodexLogin();
			updateProviderProjection(providerId, enrollment.provider);
			if (providerId === "mimo-code") setMimoKey("");
			await modelCatalog.refresh();
			setMessage(
				providerId === "mimo-code"
					? "MiMo Code подключён."
					: "Вход Codex CLI подтверждён.",
			);
		} catch (error) {
			setFailed(true);
			setMessage(
				error instanceof Error ? error.message : "Подключение не выполнено.",
			);
		} finally {
			setBusy(null);
		}
	};

	const startDurableEnrollment = async (providerId: ProviderId) => {
		setBusy(`enroll:${providerId}`);
		setFailed(false);
		setMessage(null);
		try {
			const enrollment = await startProviderEnrollment(
				providerId,
				createProviderEnrollmentNonce(),
			);
			updateProviderProjection(providerId, enrollment.provider);
			await modelCatalog.refresh();
			setMessage(
				enrollment.provider.status === "connected"
					? `${enrollment.provider.displayName} подключён.`
					: `Запрос на подключение ${enrollment.provider.displayName} отправлен.`,
			);
		} catch (error) {
			setFailed(true);
			setMessage(
				error instanceof Error
					? error.message
					: "Запрос на подключение не выполнен.",
			);
		} finally {
			setBusy(null);
		}
	};

	const refreshProviderConnections = async () => {
		setBusy("refresh");
		try {
			const refreshed = await load();
			if (refreshed) {
				await modelCatalog.refresh();
			}
		} finally {
			setBusy(null);
		}
	};

	return (
		<section>
			<SectionHeading
				icon={Bot}
				title="ИИ и модели"
				description={
					identity.user?.isPlatformOwner
						? "Выберите модель для новых сообщений. Доступность проверяется перед каждым запросом."
						: "Модели и провайдеры настраивает администратор платформы."
				}
			/>

			<div className="mt-6">
				<h3 className="text-[13px] font-semibold">Модель по умолчанию</h3>
				{identity.user?.isPlatformOwner ? (
					<>
						<p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
							Этот же селектор используется в чате: модель, усилие рассуждения и
							скорость применяются к новым сообщениям.
						</p>
						<div className="mt-3 max-w-md">
							<AgentProfileSelector surface="settings" />
						</div>
					</>
				) : (
					<p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
						Выбор модели недоступен пользователям — модель назначает
						администратор платформы.
					</p>
				)}
			</div>

			<div className="mt-6">
				<h3 className="text-[13px] font-semibold">Dev-режим</h3>
				<p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
					Режим применяется к новым сообщениям: выключено, с подтверждением
					или полный доступ.
				</p>
				<div className="mt-3 max-w-md">
					<AgentProfileSelector surface="settings" control="developer" />
				</div>
			</div>

			{message ? (
				<p
					className={cn(
						"mt-4 rounded-xl px-3 py-2 text-[12px] leading-5",
						failed
							? "border border-destructive/30 text-destructive"
							: "bg-muted/40 text-muted-foreground",
					)}
					role={failed ? "alert" : "status"}
				>
					{message}
				</p>
			) : null}

			{isSuperadmin ? (
				<section className="mt-8 border-t pt-6">
					<div className="flex flex-wrap items-start justify-between gap-4">
						<div>
							<h3 className="text-[13px] font-semibold">
								Подключения провайдеров
							</h3>
							<p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
								{LOCAL_PROVIDER_CONNECTIONS_ENABLED
									? "Ключ отправляется только при нажатии «Подключить», не сохраняется в профиле или чате и после отправки удаляется из поля."
									: "Подключение запускается защищённым серверным запросом. Секреты провайдера не проходят через браузер или Product API."}
							</p>
						</div>
						<Button
							type="button"
							variant="outline"
							size="sm"
							disabled={loading || busy !== null}
							onClick={() => void refreshProviderConnections()}
							className="rounded-lg shadow-none"
						>
							<RefreshCw
								className={cn(
									"size-4",
									(loading || busy === "refresh") && "animate-spin",
								)}
								aria-hidden="true"
							/>
							Обновить
						</Button>
					</div>

					{!loading &&
					providers &&
					!providers.authorityConfigured &&
					providers.providers.every(
						(provider) => provider.status !== "connected",
					) ? (
						<p
							className="text-muted-foreground mt-4 rounded-xl border px-3 py-2 text-[12px] leading-5"
							role="status"
						>
							{LOCAL_PROVIDER_CONNECTIONS_ENABLED
								? "Центральное подключение пока не настроено. Ниже можно подключить модель для этого рабочего пространства."
								: "Provider Execution Authority пока не настроен. Защищённое подключение станет доступно после настройки серверного контура."}
						</p>
					) : null}

					<div className="mt-4 space-y-3">
						<ProviderCard
							provider={mimoProvider}
							fallbackId="mimo-code"
							icon={Code2}
							loading={loading}
						>
							{LOCAL_PROVIDER_CONNECTIONS_ENABLED ? (
								<form
									className="mt-4 flex flex-col gap-2 sm:flex-row"
									onSubmit={(event) => {
										event.preventDefault();
										void connectLocalProvider("mimo-code");
									}}
								>
									<Input
										type="password"
										autoComplete="off"
										spellCheck={false}
										value={mimoKey}
										onChange={(event) => setMimoKey(event.target.value)}
										placeholder={
											mimoConnected ? "Новый API-ключ MiMo" : "API-ключ MiMo"
										}
										aria-label={
											mimoConnected ? "Новый API-ключ MiMo" : "API-ключ MiMo"
										}
										disabled={busy !== null}
										className="h-9 min-w-0 flex-1 rounded-lg"
									/>
									<Button
										type="submit"
										size="sm"
										disabled={busy !== null || mimoKey.trim().length < 16}
										className="rounded-lg shadow-none"
									>
										{busy === "connect:mimo-code" ? (
											<LoaderCircle className="size-4 animate-spin" />
										) : (
											<KeyRound className="size-4" />
										)}
										{mimoConnected ? "Заменить ключ" : "Подключить"}
									</Button>
								</form>
							) : (
								<Button
									type="button"
									size="sm"
									disabled={
										busy !== null ||
										mimoProvider?.status === "connected" ||
										mimoProvider?.status === "pending" ||
										providers?.authorityConfigured !== true
									}
									onClick={() => void startDurableEnrollment("mimo-code")}
									className="mt-4 rounded-lg shadow-none"
								>
									{busy === "enroll:mimo-code" ? (
										<LoaderCircle className="size-4 animate-spin" />
									) : (
										<Plug className="size-4" />
									)}
									{mimoConnected
										? "MiMo подключён"
										: mimoProvider?.status === "pending"
											? "Запрос отправлен"
											: "Подключить MiMo"}
								</Button>
							)}
						</ProviderCard>

						<ProviderCard
							provider={codexProvider}
							fallbackId="codex-cli"
							icon={Bot}
							loading={loading}
						>
							{LOCAL_PROVIDER_CONNECTIONS_ENABLED ? (
								<Button
									type="button"
									size="sm"
									disabled={busy !== null}
									onClick={() => void connectLocalProvider("codex-cli")}
									className="mt-4 rounded-lg shadow-none"
								>
									{busy === "connect:codex-cli" ? (
										<LoaderCircle className="size-4 animate-spin" />
									) : (
										<LogIn className="size-4" />
									)}
									{codexConnected
										? "Переподключить Codex"
										: "Подтвердить вход Codex"}
								</Button>
							) : (
								<Button
									type="button"
									size="sm"
									disabled={
										busy !== null ||
										codexProvider?.status === "connected" ||
										codexProvider?.status === "pending" ||
										providers?.authorityConfigured !== true
									}
									onClick={() => void startDurableEnrollment("codex-cli")}
									className="mt-4 rounded-lg shadow-none"
								>
									{busy === "enroll:codex-cli" ? (
										<LoaderCircle className="size-4 animate-spin" />
									) : (
										<LogIn className="size-4" />
									)}
									{codexConnected
										? "Codex подключён"
										: codexProvider?.status === "pending"
											? "Запрос отправлен"
											: "Подключить Codex"}
								</Button>
							)}
						</ProviderCard>
					</div>
				</section>
			) : (
				<p className="text-muted-foreground mt-8 border-t pt-5 text-[12px] leading-5">
					Подключениями моделей управляет суперадминистратор. Вы можете выбрать
					любую из уже доступных моделей.
				</p>
			)}

			<UserModelsSection />
		</section>
	);
}

function ProviderCard({
	children,
	fallbackId,
	icon: Icon,
	loading,
	provider,
}: {
	children?: React.ReactNode;
	fallbackId: ProviderId;
	icon: LucideIcon;
	loading: boolean;
	provider?: ProviderProjection;
}) {
	const title =
		provider?.displayName ??
		(fallbackId === "mimo-code" ? "MiMo Code" : "Codex CLI");
	const ready = provider?.status === "connected";
	const statusLabel = loading
		? "Проверяем"
		: ready
			? provider.statusLabel
			: (provider?.statusLabel ?? "Не подключён");

	return (
		<article className="rounded-2xl border bg-card p-4">
			<div className="flex items-start gap-3">
				<div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted">
					<Icon className="size-5 text-muted-foreground" aria-hidden="true" />
				</div>
				<div className="min-w-0 flex-1">
					<div className="flex flex-wrap items-center gap-2">
						<h3 className="text-[14px] font-semibold">{title}</h3>
						<span
							className={cn(
								"rounded-full border px-2 py-0.5 text-[11px] font-medium",
								ready
									? "border-emerald-600/30 text-emerald-700"
									: provider?.status === "error"
										? "border-destructive/30 text-destructive"
										: "text-muted-foreground",
							)}
						>
							{statusLabel}
						</span>
					</div>
					<p className="text-muted-foreground mt-1 text-[12px] leading-5">
						{loading
							? "Проверяем подключение."
							: ready
								? "Модель готова к работе."
								: provider?.status === "pending"
									? "Подключение ожидает подтверждения."
									: provider?.status === "error"
										? "Подключение требует внимания."
										: "Модель пока не подключена."}
					</p>
				</div>
			</div>
			{children}
		</article>
	);
}

function SecuritySection() {
	const identity = useIdentity();
	const [loggingOut, setLoggingOut] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const logout = async () => {
		setLoggingOut(true);
		setError(null);
		try {
			await identity.logout();
		} catch (requestError) {
			setError(
				requestError instanceof Error
					? requestError.message
					: "Не удалось завершить сессию.",
			);
		} finally {
			setLoggingOut(false);
		}
	};

	return (
		<section>
			<SectionHeading
				icon={ShieldCheck}
				title="Безопасность"
				description="Данные входа и ключи моделей защищены и не показываются интерфейсу."
			/>
			<div className="mt-6 rounded-2xl border bg-card p-5">
				<div className="flex items-start gap-3">
					<KeyRound
						className="mt-0.5 size-5 text-muted-foreground"
						aria-hidden="true"
					/>
					<div>
						<h3 className="text-[14px] font-semibold">Текущая сессия</h3>
						<p className="text-muted-foreground mt-1 text-[12px] leading-5">
							Вы вошли как {identity.user?.email}. Сессия проверяется при каждом
							защищённом действии.
						</p>
					</div>
				</div>
				<Button
					type="button"
					variant="outline"
					size="sm"
					disabled={loggingOut}
					onClick={() => void logout()}
					className="mt-5 rounded-lg shadow-none"
				>
					{loggingOut ? (
						<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
					) : (
						<LogOut className="size-4" aria-hidden="true" />
					)}
					Выйти на этом устройстве
				</Button>
				{error ? (
					<p className="mt-3 text-[12px] text-destructive" role="alert">
						{error}
					</p>
				) : null}
			</div>
		</section>
	);
}

function SectionHeading({
	description,
	icon: Icon,
	title,
}: {
	description: string;
	icon: LucideIcon;
	title: string;
}) {
	return (
		<div data-slot="settings-section-heading">
			<div className="flex items-center gap-2.5">
				<Icon className="text-muted-foreground size-5" aria-hidden="true" />
				<h2 className="text-2xl font-semibold tracking-[-0.025em]">{title}</h2>
			</div>
			<p className="text-muted-foreground mt-2 max-w-2xl text-[13px] leading-5">
				{description}
			</p>
		</div>
	);
}

const USER_PROVIDER_OPTIONS = [
	{ value: "openai", label: "OpenAI" },
	{ value: "anthropic", label: "Anthropic" },
	{ value: "qwen", label: "Qwen" },
	{ value: "custom", label: "Custom (OpenAI-compatible)" },
] as const;

function UserModelsSection() {
	const modelCatalog = useModelCatalog();
	const [models, setModels] = useState<UserManagedModel[]>([]);
	const [loading, setLoading] = useState(true);
	const [showForm, setShowForm] = useState(false);
	const [busy, setBusy] = useState<string | null>(null);
	const [message, setMessage] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);

	// Form state
	const [providerType, setProviderType] = useState("openai");
	const [modelId, setModelId] = useState("");
	const [displayName, setDisplayName] = useState("");
	const [apiKey, setApiKey] = useState("");
	const [baseUrl, setBaseUrl] = useState("");
	const [autoPriority, setAutoPriority] = useState("50");

	const load = useCallback(async (signal?: AbortSignal) => {
		setLoading(true);
		try {
			setModels(await getUserModels(signal));
		} catch {
			// Silently fail — user may not have any models yet
		} finally {
			if (!signal?.aborted) setLoading(false);
		}
	}, []);

	useEffect(() => {
		const controller = new AbortController();
		void load(controller.signal);
		return () => controller.abort();
	}, [load]);

	const resetForm = () => {
		setProviderType("openai");
		setModelId("");
		setDisplayName("");
		setApiKey("");
		setBaseUrl("");
		setAutoPriority("50");
	};

	const handleCreate = async (event: FormEvent) => {
		event.preventDefault();
		setBusy("create");
		setMessage(null);
		setFailed(false);
		try {
			const payload: UserModelCreate = {
				providerType,
				modelId,
				displayName,
				apiKey,
				baseUrl: providerType === "custom" ? baseUrl : undefined,
				autoPriority: Number(autoPriority) || 50,
			};
			const created = await createUserModel(payload);
			setModels((prev) => [created, ...prev]);
			setMessage(`Модель «${created.displayName}» подключена.`);
			resetForm();
			setShowForm(false);
			await modelCatalog.refresh();
		} catch (err) {
			setFailed(true);
			setMessage(
				err instanceof Error ? err.message : "Не удалось подключить модель.",
			);
		} finally {
			setBusy(null);
		}
	};

	const handleTest = async (id: string) => {
		setBusy(`test:${id}`);
		setMessage(null);
		setFailed(false);
		try {
			const result = await testUserModel(id);
			setMessage(result.message);
			setFailed(result.status !== "connected");
			setModels((prev) =>
				prev.map((m) =>
					m.id === id
						? { ...m, lastTestStatus: result.status, lastTestedAt: new Date().toISOString() }
						: m,
				),
			);
		} catch (err) {
			setFailed(true);
			setMessage(
				err instanceof Error ? err.message : "Ошибка тестирования.",
			);
		} finally {
			setBusy(null);
		}
	};

	const handleToggle = async (id: string, enabled: boolean) => {
		setBusy(`toggle:${id}`);
		setMessage(null);
		setFailed(false);
		try {
			const updated = await updateUserModel(id, { isEnabled: !enabled });
			setModels((prev) => prev.map((m) => (m.id === id ? updated : m)));
			await modelCatalog.refresh();
		} catch (err) {
			setFailed(true);
			setMessage(
				err instanceof Error ? err.message : "Ошибка обновления.",
			);
		} finally {
			setBusy(null);
		}
	};

	const handleDelete = async (id: string) => {
		setBusy(`delete:${id}`);
		setMessage(null);
		setFailed(false);
		try {
			await deleteUserModel(id);
			setModels((prev) => prev.filter((m) => m.id !== id));
			await modelCatalog.refresh();
			setMessage("Модель удалена.");
		} catch (err) {
			setFailed(true);
			setMessage(
				err instanceof Error ? err.message : "Ошибка удаления.",
			);
		} finally {
			setBusy(null);
		}
	};

	return (
		<section className="mt-8 border-t pt-6">
			<div className="flex items-start justify-between gap-4">
				<div>
					<h3 className="text-[13px] font-semibold">Мои модели</h3>
					<p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
						Подключите дополнительные модели со своими API-ключами. Они появятся
						в каталоге моделей для выбора.
					</p>
				</div>
				<Button
					type="button"
					variant="outline"
					size="sm"
					onClick={() => setShowForm(!showForm)}
					className="rounded-lg shadow-none"
				>
					<Plus className="size-4" aria-hidden="true" />
					{showForm ? "Скрыть" : "Добавить модель"}
				</Button>
			</div>

			{showForm ? (
				<form
					onSubmit={(e) => void handleCreate(e)}
					className="mt-4 space-y-3 rounded-2xl border bg-card p-4"
				>
					<div className="grid gap-3 sm:grid-cols-2">
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">
								Провайдер
							</label>
							<select
								value={providerType}
								onChange={(e) => setProviderType(e.target.value)}
								className="h-10 w-full rounded-xl border bg-background px-3 text-[12px] shadow-none"
							>
								{USER_PROVIDER_OPTIONS.map((opt) => (
									<option key={opt.value} value={opt.value}>
										{opt.label}
									</option>
								))}
							</select>
						</div>
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">Model ID *</label>
							<Input value={modelId} onChange={(e) => setModelId(e.target.value)} placeholder="gpt-4o" className="h-10 rounded-xl text-[12px] shadow-none" />
						</div>
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">Название *</label>
							<Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="GPT-4o" className="h-10 rounded-xl text-[12px] shadow-none" />
						</div>
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">
								API ключ *
							</label>
							<Input
								type="password"
								value={apiKey}
								onChange={(e) => setApiKey(e.target.value)}
								placeholder="sk-..."
								className="h-10 rounded-xl text-[12px] shadow-none"
							/>
						</div>
						{providerType === "custom" ? (
							<div className="space-y-1.5">
								<label className="text-[12px] font-medium text-muted-foreground">Base URL *</label>
								<Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" className="h-10 rounded-xl text-[12px] shadow-none" />
							</div>
						) : null}
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">Приоритет (0–100)</label>
							<Input value={autoPriority} onChange={(e) => setAutoPriority(e.target.value)} inputMode="numeric" placeholder="50" className="h-10 rounded-xl text-[12px] shadow-none" />
						</div>
					</div>
					<div className="flex gap-2">
						<Button
							type="submit"
							size="sm"
							disabled={busy !== null || !modelId || !displayName || !apiKey}
							className="rounded-lg shadow-none"
						>
							{busy === "create" ? (
								<LoaderCircle className="size-4 animate-spin" />
							) : (
								<Plus className="size-4" />
							)}
							Подключить
						</Button>
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={() => {
								setShowForm(false);
								resetForm();
							}}
							className="rounded-lg shadow-none"
						>
							Отмена
						</Button>
					</div>
				</form>
			) : null}

			{message ? (
				<p
					className={cn(
						"mt-3 rounded-xl px-3 py-2 text-[12px]",
						failed
							? "border border-destructive/30 text-destructive"
							: "bg-muted/40 text-muted-foreground",
					)}
					role={failed ? "alert" : "status"}
				>
					{message}
				</p>
			) : null}

			{loading ? (
				<div className="text-muted-foreground mt-4 flex items-center gap-2 text-[12px]">
					<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
					Загрузка моделей…
				</div>
			) : models.length ? (
				<div className="mt-4 space-y-2">
					{models.map((model) => (
						<article
							key={model.id}
							className="rounded-2xl border bg-card p-4"
						>
							<div className="flex items-start justify-between gap-3">
								<div className="min-w-0 flex-1">
									<div className="flex items-center gap-2">
										<p className="truncate text-[13px] font-semibold">
											{model.displayName}
										</p>
										<span
											className={cn(
												"rounded-full border px-2 py-0.5 text-[11px] font-medium",
												model.isEnabled
													? "border-emerald-600/30 text-emerald-700"
													: "text-muted-foreground",
											)}
										>
											{model.isEnabled ? "Включена" : "Отключена"}
										</span>
										<span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
											{model.providerType}
										</span>
									</div>
									<p className="text-muted-foreground mt-1 truncate text-[11px]">
										{model.modelId}
										{model.baseUrl ? ` · ${model.baseUrl}` : ""}
										{` · приоритет ${model.autoPriority}`}
									</p>
									{model.lastTestedAt ? (
										<p className="text-muted-foreground mt-1 text-[10px]">
											Тест:{" "}
											{new Date(model.lastTestedAt).toLocaleString("ru-RU")} —{" "}
											{model.lastTestStatus === "connected"
												? "успешно"
												: model.lastTestStatus ?? "—"}
										</p>
									) : null}
								</div>
								<div className="flex shrink-0 items-center gap-1">
									<Button
										type="button"
										variant="outline"
										size="sm"
										disabled={busy !== null}
										onClick={() => void handleTest(model.id)}
										className="rounded-lg shadow-none"
										title="Тестировать"
									>
										{busy === `test:${model.id}` ? (
											<LoaderCircle className="size-4 animate-spin" />
										) : (
											<TestTube2 className="size-4" />
										)}
									</Button>
									<Button
										type="button"
										variant="outline"
										size="sm"
										disabled={busy !== null}
										onClick={() =>
											void handleToggle(model.id, model.isEnabled)
										}
										className="rounded-lg shadow-none"
										title={model.isEnabled ? "Отключить" : "Включить"}
									>
										{busy === `toggle:${model.id}` ? (
											<LoaderCircle className="size-4 animate-spin" />
										) : (
											<Check
												className={cn(
													"size-4",
													!model.isEnabled && "opacity-30",
												)}
											/>
										)}
									</Button>
									<Button
										type="button"
										variant="outline"
										size="sm"
										disabled={busy !== null}
										onClick={() => void handleDelete(model.id)}
										className="rounded-lg shadow-none text-destructive hover:text-destructive"
										title="Удалить"
									>
										{busy === `delete:${model.id}` ? (
											<LoaderCircle className="size-4 animate-spin" />
										) : (
											<Trash2 className="size-4" />
										)}
									</Button>
								</div>
							</div>
						</article>
					))}
				</div>
			) : (
				<p className="text-muted-foreground mt-4 text-[12px]">
					У вас нет подключённых моделей. Нажмите «Добавить модель», чтобы
					подключить свою первую модель.
				</p>
			)}
		</section>
	);
}
