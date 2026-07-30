"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type KolibriThemePreference,
  useKolibriTheme,
} from "@/components/theme/kolibri-theme-provider";
import { AgentProfileSelector } from "@/components/assistant-ui/agent-profile-selector";
import { PlatformAdminSection } from "@/components/kolibri-shell/platform-admin-section";
import {
  KOLIBRI_PETS,
  KOLIBRI_PET_SELECTION_EVENT,
  KOLIBRI_PET_VISIBILITY_EVENT,
  KOLIBRI_PET_VISIBILITY_KEY,
  PetAvatar,
  readKolibriPetId,
  readKolibriPetVisibility,
  setKolibriPetId,
  setKolibriPetVisibility,
  type KolibriPetId,
} from "@/components/kolibri-shell/kolibri-pet";
import {
  accountInitials,
  type AgentProfile,
} from "@/lib/identity/contracts";
import { useIdentity } from "@/lib/identity/provider";
import { useModelCatalog } from "@/lib/models/provider";
import {
  connectCodexLogin,
  connectMimo,
  createProviderEnrollmentNonce,
  getProviders,
  LOCAL_PROVIDER_CONNECTIONS_ENABLED,
  startProviderEnrollment,
  type ProviderId,
  type ProviderList,
  type ProviderProjection,
} from "@/lib/providers/client";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  Bird,
  Bot,
  Check,
  ChevronRight,
  Code2,
  CreditCard,
  Filter,
  KeyRound,
  LoaderCircle,
  LogIn,
  LogOut,
  Monitor,
  Moon,
  Palette,
  Plug,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Store,
  Sun,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

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
  onClose: () => void;
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

const PROFILE_PRESENTATION: Record<
  AgentProfile,
  { label: string; description: string }
> = {
  auto: {
    label: "Авто",
    description: "Kolibri выберет доступную модель для задачи.",
  },
  "mimo-code": {
    label: "MiMo Code",
    description: "Быстрая модель для повседневных запросов.",
  },
  "codex-cli": {
    label: "Codex",
    description: "Модель для сложных задач, анализа и кода.",
  },
};

export function ProfileSettingsSurface({
  activeSection: controlledSection,
  onClose,
  onSectionChange,
  initialSection = "general",
}: ProfileSettingsSurfaceProps) {
  const identity = useIdentity();
  const [internalSection, setInternalSection] =
    useState<ProfileSettingsSection>(initialSection);
  const activeSection = controlledSection ?? internalSection;
  const [search, setSearch] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(
    controlledSection === undefined || controlledSection === "general",
  );
  const mobileMenuRef = useRef<HTMLElement>(null);
  const selectSection = (section: ProfileSettingsSection) => {
    setInternalSection(section);
    onSectionChange?.(section);
    setMobileMenuOpen(false);
  };
  const showMobileMenu = () => {
    setMobileMenuOpen(true);
    window.requestAnimationFrame(() => {
      mobileMenuRef.current?.scrollTo({ top: 0 });
    });
  };

  useEffect(() => {
    if (controlledSection === undefined) {
      setInternalSection(initialSection);
    }
  }, [controlledSection, initialSection]);

  const roleLabel =
    identity.user?.isPlatformOwner
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
  const activeSectionLabel =
    SECTION_GROUPS.flatMap((group) => group.sections).find(
      (section) => section.id === activeSection,
    )?.label ?? "Настройки";

  return (
    <section
      data-slot="account-settings-surface"
      aria-label="Личный кабинет Kolibri"
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background"
    >
      {identity.status === "loading" ? (
        <LoadingAccount />
      ) : identity.status !== "authenticated" || !identity.user ? (
        <>
          <div className="flex min-h-12 shrink-0 items-center border-b px-3 sm:px-5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="rounded-lg"
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
              К чату
            </Button>
          </div>
          <AuthPanel onAuthenticated={onClose} />
        </>
      ) : (
        <div
          data-slot="account-settings-layout"
          className="grid min-h-0 flex-1 grid-cols-1 grid-rows-1 min-[960px]:grid-cols-[minmax(250px,320px)_minmax(0,1fr)]"
        >
          <aside
            ref={mobileMenuRef}
            aria-label="Разделы личного кабинета"
            data-slot="account-settings-menu"
            className={cn(
              "h-full min-h-0 overflow-y-auto bg-[#f2f2f7] px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[calc(1rem+env(safe-area-inset-top))] dark:bg-[#242426] min-[960px]:block min-[960px]:border-r min-[960px]:border-[#dce5f5] min-[960px]:bg-[#eef3ff] min-[960px]:px-4 min-[960px]:py-6 min-[960px]:dark:border-sky-950 min-[960px]:dark:bg-[#101721]",
              mobileMenuOpen ? "block" : "hidden",
            )}
          >
            <div
              data-slot="account-mobile-profile"
              className="relative flex min-h-[16.5rem] flex-col items-center justify-end pb-5 min-[960px]:hidden"
            >
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onClose}
                aria-label="Закрыть личный кабинет"
                className="absolute top-0 right-0 size-12 rounded-full border border-foreground/45 bg-transparent p-0 shadow-none"
              >
                <X aria-hidden="true" className="size-8 stroke-[1.8]" />
              </Button>
              <span
                aria-hidden="true"
                className="flex size-[92px] items-center justify-center rounded-full bg-[#fb927c] text-[28px] font-medium text-white"
              >
                {accountInitials(identity.user)}
              </span>
              <p className="mt-3 max-w-full truncate text-[22px] leading-7 font-semibold tracking-[-0.025em]">
                {identity.user.name}
              </p>
              <p className="text-muted-foreground mt-1 text-[15px]">
                {roleLabel}
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="text-muted-foreground -ml-2 hidden h-9 rounded-lg px-2 hover:bg-white/70 hover:text-foreground dark:hover:bg-white/[0.06] min-[960px]:inline-flex"
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
              Вернуться в приложение
            </Button>
            <div className="mt-4 hidden items-center gap-2 px-1 text-[15px] font-medium min-[960px]:flex">
              <Filter className="size-4" />
              Все настройки
            </div>
            <div className="relative mt-5 hidden min-[960px]:block">
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
                className="h-10 rounded-xl border-white/80 bg-white/85 pl-9 shadow-sm dark:border-white/10 dark:bg-white/[0.06]"
              />
            </div>
            <nav
              data-slot="account-settings-navigation"
              className="mt-5 min-[960px]:mt-5"
              aria-label="Все настройки"
            >
              {filteredGroups.length ? (
                filteredGroups.map((group) => (
                  <div
                    key={group.label}
                    data-slot="account-settings-group"
                    className="mb-7 min-[960px]:mb-5"
                  >
                    <h2 className="text-muted-foreground mb-2 px-2 text-[17px] font-semibold tracking-[-0.02em] min-[960px]:mb-1.5 min-[960px]:text-[11px] min-[960px]:font-medium min-[960px]:uppercase min-[960px]:tracking-wide">
                      {group.label}
                    </h2>
                    <ul className="divide-y divide-foreground/10 overflow-hidden rounded-[26px] bg-white px-4 dark:bg-[#373739] min-[960px]:space-y-0.5 min-[960px]:divide-y-0 min-[960px]:overflow-visible min-[960px]:rounded-none min-[960px]:bg-transparent min-[960px]:px-0 min-[960px]:dark:bg-transparent">
                      {group.sections.map(({ id, icon: Icon, label }) => (
                        <li key={id}>
                          <button
                            type="button"
                            aria-current={
                              activeSection === id ? "page" : undefined
                            }
                            onClick={() => selectSection(id)}
                            className={cn(
                              "flex min-h-[56px] w-full items-center gap-3 text-left text-[17px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-sky-400/50 min-[960px]:min-h-9 min-[960px]:gap-2.5 min-[960px]:rounded-lg min-[960px]:px-2.5 min-[960px]:text-[13px] min-[960px]:font-normal",
                              activeSection === id
                                ? "text-foreground min-[960px]:bg-[#d8e4fa] min-[960px]:dark:bg-sky-900/45"
                                : "min-[960px]:hover:bg-[#e2edff] min-[960px]:dark:hover:bg-sky-950/45",
                            )}
                          >
                            <Icon
                              className="size-[22px] shrink-0 stroke-[1.8] min-[960px]:size-4"
                              aria-hidden="true"
                            />
                            <span className="truncate">{label}</span>
                            <ChevronRight
                              aria-hidden="true"
                              className="text-muted-foreground ml-auto size-5 shrink-0 stroke-[2.4] min-[960px]:hidden"
                            />
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
            <div className="mt-4 hidden items-center gap-2.5 border-t border-sky-200/60 px-2 pt-4 dark:border-sky-900/60 min-[960px]:flex">
              <span className="flex size-7 items-center justify-center rounded-full bg-[#fb927c] text-[10px] font-medium text-white">
                {accountInitials(identity.user)}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium">
                  {identity.user.name}
                </span>
                <span className="text-muted-foreground block truncate text-[10px]">
                  {roleLabel}
                </span>
              </span>
            </div>
          </aside>

          <main
            data-slot="account-settings-detail"
            className={cn(
              "h-full min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#f2f2f7] px-4 pb-[max(2rem,env(safe-area-inset-bottom))] dark:bg-[#242426] min-[960px]:block min-[960px]:bg-background min-[960px]:px-12 min-[960px]:py-10 min-[960px]:dark:bg-background",
              mobileMenuOpen ? "hidden" : "block",
            )}
          >
            <div
              data-slot="account-mobile-detail-header"
              className="sticky top-0 z-10 -mx-4 mb-5 grid min-h-[calc(5rem+env(safe-area-inset-top))] grid-cols-[48px_minmax(0,1fr)_48px] items-end gap-2 bg-[#f2f2f7] px-4 pb-3 dark:bg-[#242426] min-[960px]:hidden"
            >
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={showMobileMenu}
                aria-label="К списку настроек"
                className="size-12 rounded-full border border-foreground/45 bg-transparent p-0 shadow-none"
              >
                <ArrowLeft className="size-7" aria-hidden="true" />
              </Button>
              <h1 className="self-center truncate text-center text-[19px] font-semibold tracking-[-0.025em]">
                {activeSectionLabel}
              </h1>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onClose}
                aria-label="Закрыть личный кабинет"
                className="size-12 rounded-full border border-foreground/45 bg-transparent p-0 shadow-none"
              >
                <X aria-hidden="true" className="size-7" />
              </Button>
            </div>
            <div
              data-slot="account-settings-content"
              className="mx-auto w-full max-w-[860px]"
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
  if (section === "billing") {
    return (
      <EmptyProductSection
        icon={CreditCard}
        title="Использование и оплата"
        description="Здесь появятся фактическое использование моделей, тариф и документы оплаты."
        empty="Биллинг пока не подключён к этому рабочему пространству."
      />
    );
  }
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

function AuthPanel({
  onAuthenticated,
}: {
  onAuthenticated: () => void;
}) {
  const identity = useIdentity();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(identity.error);

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
      <div className="mx-auto w-full max-w-md">
        <div className="flex size-11 items-center justify-center rounded-2xl bg-neutral-950 text-white">
          <LogIn className="size-5" aria-hidden="true" />
        </div>
        <h2 className="mt-5 text-xl font-semibold tracking-tight">
          {mode === "login" ? "Войти в Kolibri" : "Создать аккаунт"}
        </h2>
        <p className="text-muted-foreground mt-1 text-sm leading-5">
          Чаты, проекты и настройки сохраняются в вашем пространстве Kolibri.
        </p>

        <div
          role="tablist"
          aria-label="Способ входа"
          className="mt-6 grid grid-cols-2 rounded-xl bg-muted p-1"
        >
          <button
            type="button"
            role="tab"
            id="account-login-tab"
            aria-controls="account-auth-panel"
            aria-selected={mode === "login"}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={cn(
              "h-9 rounded-lg text-sm font-medium",
              mode === "login" ? "bg-background shadow-sm" : "text-muted-foreground",
            )}
          >
            Вход
          </button>
          <button
            type="button"
            role="tab"
            id="account-register-tab"
            aria-controls="account-auth-panel"
            aria-selected={mode === "register"}
            onClick={() => {
              setMode("register");
              setError(null);
            }}
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

        <form
          id="account-auth-panel"
          role="tabpanel"
          aria-labelledby={
            mode === "login" ? "account-login-tab" : "account-register-tab"
          }
          className="mt-5 space-y-4"
          onSubmit={submit}
        >
          {mode === "register" ? (
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
          ) : null}
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
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
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
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : null}
            {mode === "login" ? "Войти" : "Создать аккаунт"}
          </Button>
        </form>

        {identity.status === "offline" ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void identity.refresh()}
            className="mt-3 w-full rounded-lg"
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            Повторить подключение
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function GeneralSection() {
  const identity = useIdentity();
  const selectedModel = identity.user
    ? PROFILE_PRESENTATION[identity.user.preferredAgentProfile].label
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
  const [selectedPet, setSelectedPet] =
    useState<KolibriPetId>("kolibri");
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    setSelectedPet(readKolibriPetId());
    setVisible(readKolibriPetVisibility());

    const syncVisibility = (event: Event) => {
      const next = (
        event as CustomEvent<{ visible?: unknown }>
      ).detail?.visible;
      if (typeof next === "boolean") setVisible(next);
    };
    const syncSelection = (event: Event) => {
      const next = (
        event as CustomEvent<{ id?: unknown }>
      ).detail?.id;
      if (KOLIBRI_PETS.some((pet) => pet.id === next)) {
        setSelectedPet(next as KolibriPetId);
      }
    };

    globalThis.addEventListener(
      KOLIBRI_PET_VISIBILITY_EVENT,
      syncVisibility,
    );
    globalThis.addEventListener(
      KOLIBRI_PET_SELECTION_EVENT,
      syncSelection,
    );
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
                  <Check className="size-3" />
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
        <p data-slot="settings-content-title" className="text-[14px] font-medium">
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
      setMessage(error instanceof Error ? error.message : "Профиль не сохранён.");
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
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
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

  const load = useCallback(async (signal?: AbortSignal) => {
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
  }, [isSuperadmin]);

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
        error instanceof Error
          ? error.message
          : "Подключение не выполнено.",
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
        description="Выберите модель для новых сообщений. Доступность проверяется перед каждым запросом."
      />

      <div className="mt-6">
        <h3 className="text-[13px] font-semibold">Модель по умолчанию</h3>
        <p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
          Этот же селектор используется в чате: модель, усилие рассуждения и
          скорость применяются к новым сообщениям.
        </p>
        <div className="mt-3 max-w-md">
          <AgentProfileSelector surface="settings" />
        </div>
      </div>

      <div className="mt-6">
        <h3 className="text-[13px] font-semibold">Dev-режим</h3>
        <p className="text-muted-foreground mt-1 max-w-xl text-[12px] leading-5">
          То же явное переключение доступно в композере: выключено, с
          подтверждением или полный доступ.
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
      : provider?.statusLabel ?? "Не подключён";

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
          <KeyRound className="mt-0.5 size-5 text-muted-foreground" aria-hidden="true" />
          <div>
            <h3 className="text-[14px] font-semibold">Текущая сессия</h3>
            <p className="text-muted-foreground mt-1 text-[12px] leading-5">
              Вы вошли как {identity.user?.email}. Сессия проверяется при
              каждом защищённом действии.
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
