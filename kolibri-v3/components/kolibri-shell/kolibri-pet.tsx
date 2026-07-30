"use client";

import {
  ArrowUp,
  ChevronsLeftRight,
  PanelRightOpen,
  Square,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";

import {
  ComposerPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { useIdentity } from "@/lib/identity/provider";
import { cn } from "@/lib/utils";

export type KolibriPetId =
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

export type KolibriPetDefinition = {
  accent: string;
  animation: string;
  asset: string;
  assetSlug: string;
  description: string;
  id: KolibriPetId;
  moods: readonly [string, string, string, string];
  name: string;
  personality: string;
  role: string;
  thumbnail: string;
};

export const KOLIBRI_PETS = [
  {
    accent: "#24c7d4",
    animation: "Радостный взмах",
    asset: "/pets/active/kolibri-v1.webp",
    assetSlug: "kolibri",
    description: "Бирюзовый колибри для быстрых повседневных задач.",
    id: "kolibri",
    moods: [
      "Готов помочь",
      "Слушаю задачу",
      "Уже лечу",
      "Всё под контролем",
    ],
    name: "Коли",
    personality: "Энергичный и внимательный",
    role: "Универсал",
    thumbnail: "/pets/thumbs/kolibri-v1.webp",
  },
  {
    accent: "#b6a1f2",
    animation: "Раскрывает крылья",
    asset: "/pets/active/lumi-v1.webp",
    assetSlug: "lumi",
    description: "Лунный мотылёк для тихой, глубокой концентрации.",
    id: "lumi",
    moods: [
      "Сохраняю тишину",
      "Фокус включён",
      "Вижу тонкую связь",
      "Мысль стала яснее",
    ],
    name: "Луми",
    personality: "Мягкая и вдумчивая",
    role: "Фокус",
    thumbnail: "/pets/thumbs/lumi-v1.webp",
  },
  {
    accent: "#e8b782",
    animation: "Навостряет уши",
    asset: "/pets/active/fini-v1.webp",
    assetSlug: "fini",
    description: "Крылатоухий лисёнок для поиска новых возможностей.",
    id: "fini",
    moods: [
      "Слышу интересное",
      "Проверяю маршрут",
      "Нашёл зацепку",
      "Любопытство ведёт",
    ],
    name: "Фини",
    personality: "Любопытный и находчивый",
    role: "Разведчик",
    thumbnail: "/pets/thumbs/fini-v1.webp",
  },
  {
    accent: "#ff8b3d",
    animation: "Пружинистый рывок",
    asset: "/pets/active/iskra-v1.webp",
    assetSlug: "iskra",
    description: "Огненная саламандра для смелого старта и ускорения.",
    id: "spark",
    moods: [
      "Зажигаем",
      "Темп набран",
      "Прорыв рядом",
      "Энергии хватит",
    ],
    name: "Искра",
    personality: "Смелая и стремительная",
    role: "Ускоритель",
    thumbnail: "/pets/thumbs/iskra-v1.webp",
  },
  {
    accent: "#70d9de",
    animation: "Качает жабрами",
    asset: "/pets/active/runi-v1.webp",
    assetSlug: "runi",
    description: "Аквамариновый аксолотль для спокойной совместной работы.",
    id: "dewdrop",
    moods: [
      "Не спешим зря",
      "Разберём по шагам",
      "Я рядом",
      "Течение спокойное",
    ],
    name: "Руни",
    personality: "Терпеливый и добрый",
    role: "Поддержка",
    thumbnail: "/pets/thumbs/runi-v1.webp",
  },
  {
    accent: "#5b5bd6",
    animation: "Вдумчивый наклон",
    asset: "/pets/active/buki-v1.webp",
    assetSlug: "buki",
    description: "Индиговая сова для внимательной проверки деталей.",
    id: "owl",
    moods: [
      "Сверяю детали",
      "Проверяю логику",
      "Есть тонкий нюанс",
      "Теперь аккуратно",
    ],
    name: "Буки",
    personality: "Точный и рассудительный",
    role: "Ревьюер",
    thumbnail: "/pets/thumbs/buki-v1.webp",
  },
  {
    accent: "#79c99a",
    animation: "Тянется ростком",
    asset: "/pets/active/mohi-v1.webp",
    assetSlug: "mohi",
    description: "Садовая черепашка для терпеливого развития проектов.",
    id: "sprout",
    moods: [
      "Растём понемногу",
      "Основа крепкая",
      "Ещё один хороший шаг",
      "Проект приживается",
    ],
    name: "Мохи",
    personality: "Надёжный и созидательный",
    role: "Строитель",
    thumbnail: "/pets/thumbs/mohi-v1.webp",
  },
  {
    accent: "#72d8f2",
    animation: "Плывёт волной",
    asset: "/pets/active/nimbi-v1.webp",
    assetSlug: "nimbi",
    description: "Небесный скат-облачко для свободного потока идей.",
    id: "nimbi",
    moods: [
      "Ловлю идею",
      "Смотрю шире",
      "Вариант появился",
      "Плывём дальше",
    ],
    name: "Нимби",
    personality: "Мечтательный и изобретательный",
    role: "Идейник",
    thumbnail: "/pets/thumbs/nimbi-v1.webp",
  },
  {
    accent: "#3a9fa8",
    animation: "Закручивает хвост",
    asset: "/pets/active/klik-v1.webp",
    assetSlug: "klik",
    description: "Механический геккон для точного исполнения шаг за шагом.",
    id: "klik",
    moods: [
      "Контур проверен",
      "Исполняю точно",
      "Механизм работает",
      "Шаг зафиксирован",
    ],
    name: "Клик",
    personality: "Собранный и технический",
    role: "Исполнитель",
    thumbnail: "/pets/thumbs/klik-v1.webp",
  },
  {
    accent: "#f2c84b",
    animation: "Весёлый гул",
    asset: "/pets/active/zumi-v1.webp",
    assetSlug: "zumi",
    description: "Солнечный шмель для командного духа и доброго темпа.",
    id: "zumi",
    moods: [
      "Команда в сборе",
      "Отличный темп",
      "Поддерживаю",
      "У нас получится",
    ],
    name: "Зуми",
    personality: "Радостный и отзывчивый",
    role: "Мотиватор",
    thumbnail: "/pets/thumbs/zumi-v1.webp",
  },
] as const satisfies readonly KolibriPetDefinition[];

const DEFAULT_PET = KOLIBRI_PETS[0];
const PET_MOVEMENT_INSTRUCTIONS_ID = "kolibri-pet-movement-instructions";
const PET_ASSISTANT_PANEL_ID = "kolibri-pet-mini-assistant";

type PetRunState = "idle" | "thinking" | "success" | "error";

const PET_RUN_COPY: Record<PetRunState, string> = {
  idle: "Готов помочь в этом чате",
  thinking: "Работаю над ответом…",
  success: "Ответ готов",
  error: "Не удалось завершить ответ",
};

export const KOLIBRI_PET_SELECTION_EVENT = "kolibri:pet-selection-change";
export const KOLIBRI_PET_SELECTION_KEY = "kolibri.ui.pet-id";
export const KOLIBRI_PET_VISIBILITY_EVENT =
  "kolibri:pet-visibility-change";
export const KOLIBRI_PET_VISIBILITY_KEY = "kolibri.ui.pet-visible";

function isKolibriPetId(value: unknown): value is KolibriPetId {
  return KOLIBRI_PETS.some((pet) => pet.id === value);
}

function getKolibriPet(id: KolibriPetId) {
  return KOLIBRI_PETS.find((pet) => pet.id === id) ?? DEFAULT_PET;
}

export function readKolibriPetId(): KolibriPetId {
  try {
    const saved = globalThis.localStorage.getItem(KOLIBRI_PET_SELECTION_KEY);
    if (isKolibriPetId(saved)) return saved;
  } catch {
    // Use the product default when browser preferences are unavailable.
  }
  return "kolibri";
}

export function readKolibriPetVisibility() {
  try {
    return (
      globalThis.localStorage.getItem(KOLIBRI_PET_VISIBILITY_KEY) !== "false"
    );
  } catch {
    return true;
  }
}

export function setKolibriPetId(id: KolibriPetId) {
  try {
    globalThis.localStorage.setItem(KOLIBRI_PET_SELECTION_KEY, id);
  } catch {
    // The UI event still updates mounted surfaces when storage is blocked.
  }
  globalThis.dispatchEvent(
    new CustomEvent(KOLIBRI_PET_SELECTION_EVENT, { detail: { id } }),
  );
}

export function setKolibriPetVisibility(visible: boolean) {
  try {
    globalThis.localStorage.setItem(
      KOLIBRI_PET_VISIBILITY_KEY,
      String(visible),
    );
  } catch {
    // The UI event still updates mounted surfaces when storage is blocked.
  }
  globalThis.dispatchEvent(
    new CustomEvent(KOLIBRI_PET_VISIBILITY_EVENT, {
      detail: { visible },
    }),
  );
}

export function KolibriPetHost() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(readKolibriPetVisibility());
    const syncVisibility = (event: Event) => {
      const next = (
        event as CustomEvent<{ visible?: unknown }>
      ).detail?.visible;
      if (typeof next === "boolean") setVisible(next);
    };
    globalThis.addEventListener(
      KOLIBRI_PET_VISIBILITY_EVENT,
      syncVisibility,
    );
    return () =>
      globalThis.removeEventListener(
        KOLIBRI_PET_VISIBILITY_EVENT,
        syncVisibility,
      );
  }, []);

  return visible ? <KolibriPet /> : null;
}

export function PetAvatar({
  active = false,
  className,
  id,
}: {
  active?: boolean;
  className?: string;
  id: KolibriPetId;
}) {
  return (
    <span
      aria-hidden="true"
      data-active={active ? "true" : undefined}
      className={cn(
        "group/pet-avatar flex size-14 shrink-0 items-center justify-center",
        className,
      )}
    >
      <PetIllustration
        active={active}
        gaze={{ x: 0, y: 0 }}
        id={id}
        compact
      />
    </span>
  );
}

function usePetRunState(): PetRunState {
  return useAuiState((state) => {
    if (state.thread.isRunning) return "thinking";
    const last = state.thread.messages.at(-1);
    if (!last || last.role !== "assistant") return "idle";
    if (last.status.type === "complete") return "success";
    if (
      last.status.type === "incomplete" &&
      last.status.reason !== "cancelled"
    ) {
      return "error";
    }
    return "idle";
  });
}

function PetMiniAssistant({
  left,
  onClose,
  pet,
  placement,
  state,
}: {
  left: number;
  onClose: () => void;
  pet: KolibriPetDefinition;
  placement: "above" | "below";
  state: PetRunState;
}) {
  const identity = useIdentity();
  const composerEmpty = useAuiState((value) => value.composer.isEmpty);
  const running = useAuiState((value) => value.thread.isRunning);
  const authenticated = identity.status === "authenticated";

  return (
    <section
      id={PET_ASSISTANT_PANEL_ID}
      data-pet-run-state={state}
      role="dialog"
      aria-label={`Мини-помощник ${pet.name}`}
      className={cn(
        "pointer-events-auto absolute z-20 w-[min(21rem,calc(100vw-1.5rem))] rounded-3xl border border-border bg-background p-3 text-foreground shadow-2xl",
        placement === "above"
          ? "bottom-[calc(100%+0.5rem)]"
          : "top-[calc(100%+0.5rem)]",
      )}
      style={{ left }}
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        onClose();
      }}
    >
      <header className="flex min-w-0 items-center gap-2">
        <PetAvatar id={pet.id} active={state !== "idle"} className="size-12" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{pet.name}</h2>
          <p className="truncate text-xs text-muted-foreground">
            {pet.role} · {pet.personality}
          </p>
        </div>
        <button
          type="button"
          aria-label="Закрыть мини-помощника"
          className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground outline-none transition hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onClose}
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </header>
      <div
        aria-live="polite"
        className="mt-1.5 flex min-h-6 items-center gap-2 px-1 text-xs text-muted-foreground"
      >
        <span
          aria-hidden="true"
          className={cn(
            "size-2 shrink-0 rounded-full",
            state === "error"
              ? "bg-destructive"
              : state === "success"
                ? "bg-emerald-500"
                : state === "thinking"
                  ? "animate-pulse"
                  : "bg-muted-foreground",
          )}
          style={
            state === "thinking"
              ? { backgroundColor: pet.accent }
              : undefined
          }
        />
        {PET_RUN_COPY[state]}
      </div>
      <ComposerPrimitive.Root className="mt-2">
        <div className="flex min-w-0 items-end gap-1 rounded-3xl border border-border bg-background p-1.5 focus-within:ring-2 focus-within:ring-ring/40">
          <ComposerPrimitive.Input
            autoFocus
            aria-label="Сообщение питомцу в текущий чат"
            disabled={!authenticated}
            maxLength={65_536}
            placeholder={
              authenticated
                ? "Написать в этот чат…"
                : "Войдите, чтобы написать"
            }
            rows={1}
            className="max-h-28 min-h-10 min-w-0 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
          />
          {running ? (
            <ComposerPrimitive.Cancel asChild>
              <button
                type="button"
                aria-label="Остановить ответ"
                className="flex size-10 shrink-0 items-center justify-center rounded-full text-white outline-none focus-visible:ring-2 focus-visible:ring-ring"
                style={{ backgroundColor: pet.accent }}
              >
                <Square
                  aria-hidden="true"
                  className="size-3.5 fill-current"
                />
              </button>
            </ComposerPrimitive.Cancel>
          ) : (
            <ComposerPrimitive.Send asChild>
              <button
                type="button"
                aria-label="Отправить в текущий чат"
                disabled={!authenticated || composerEmpty}
                className="flex size-10 shrink-0 items-center justify-center rounded-full text-white outline-none transition disabled:bg-muted disabled:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
                style={
                  authenticated && !composerEmpty
                    ? { backgroundColor: pet.accent }
                    : undefined
                }
              >
                <ArrowUp aria-hidden="true" className="size-4.5" />
              </button>
            </ComposerPrimitive.Send>
          )}
        </div>
      </ComposerPrimitive.Root>
      <p className="mt-1.5 px-1 text-[11px] text-muted-foreground">
        Сообщение отправится в открытый диалог Product Chat.
      </p>
    </section>
  );
}

export function KolibriPet({ className }: { className?: string }) {
  const runState = usePetRunState();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const collapseButtonRef = useRef<HTMLButtonElement>(null);
  const restoreButtonRef = useRef<HTMLButtonElement>(null);
  const pendingFocusRef = useRef<"collapse" | "restore" | null>(null);
  const activeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragRef = useRef<{
    originX: number;
    originY: number;
    pointerId: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  const suppressClickRef = useRef(false);
  const [mounted, setMounted] = useState(false);
  const [petId, setPetId] = useState<KolibriPetId>("kolibri");
  const [gaze, setGaze] = useState({ x: 0, y: 0 });
  const [moodIndex, setMoodIndex] = useState(0);
  const [active, setActive] = useState(false);
  const [position, setPosition] = useState({ x: 72, y: 150 });
  const [collapsed, setCollapsed] = useState(false);
  const [collapsedSide, setCollapsedSide] = useState<"left" | "right">("left");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [reducedData, setReducedData] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const reducedDataQuery =
      typeof globalThis.matchMedia === "function"
        ? globalThis.matchMedia("(prefers-reduced-data: reduce)")
        : null;
    const reducedMotionQuery =
      typeof globalThis.matchMedia === "function"
        ? globalThis.matchMedia("(prefers-reduced-motion: reduce)")
        : null;
    const dataConnection =
      typeof globalThis.navigator === "undefined"
        ? undefined
        : (globalThis.navigator as NavigatorWithDataConnection).connection;
    const syncReducedData = () => {
      setReducedData(
        Boolean(reducedDataQuery?.matches || dataConnection?.saveData),
      );
    };
    const syncReducedMotion = () => {
      setReducedMotion(Boolean(reducedMotionQuery?.matches));
    };

    syncReducedData();
    syncReducedMotion();
    setMounted(true);
    setPetId(readKolibriPetId());
    try {
      const rawPosition = globalThis.localStorage.getItem(
        "kolibri.ui.pet-position",
      );
      if (rawPosition) {
        const saved = JSON.parse(rawPosition) as {
          x?: unknown;
          y?: unknown;
        };
        if (
          typeof saved.x === "number" &&
          Number.isFinite(saved.x) &&
          typeof saved.y === "number" &&
          Number.isFinite(saved.y)
        ) {
          setPosition(clampPetPosition({ x: saved.x, y: saved.y }));
        }
      }
      setCollapsed(
        globalThis.localStorage.getItem("kolibri.ui.pet-collapsed") === "true",
      );
      setCollapsedSide(
        globalThis.localStorage.getItem("kolibri.ui.pet-side") === "right"
          ? "right"
          : "left",
      );
    } catch {
      // The pet stays usable without durable browser preferences.
    }

    const keepInsideViewport = () => {
      setPosition((current) => clampPetPosition(current));
    };
    const syncSelection = (event: Event) => {
      const selected = (
        event as CustomEvent<{ id?: unknown }>
      ).detail?.id;
      if (isKolibriPetId(selected)) {
        setPetId(selected);
        setMoodIndex(0);
      }
    };
    globalThis.addEventListener(KOLIBRI_PET_SELECTION_EVENT, syncSelection);
    globalThis.addEventListener("resize", keepInsideViewport);
    reducedDataQuery?.addEventListener("change", syncReducedData);
    reducedMotionQuery?.addEventListener("change", syncReducedMotion);
    dataConnection?.addEventListener?.("change", syncReducedData);
    return () => {
      globalThis.removeEventListener(
        KOLIBRI_PET_SELECTION_EVENT,
        syncSelection,
      );
      globalThis.removeEventListener("resize", keepInsideViewport);
      reducedDataQuery?.removeEventListener("change", syncReducedData);
      reducedMotionQuery?.removeEventListener("change", syncReducedMotion);
      dataConnection?.removeEventListener?.("change", syncReducedData);
      if (activeTimerRef.current) clearTimeout(activeTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const pendingFocus = pendingFocusRef.current;
    if (!pendingFocus) return;
    pendingFocusRef.current = null;
    const frame = globalThis.requestAnimationFrame(() => {
      const target =
        pendingFocus === "restore"
          ? restoreButtonRef.current
          : collapseButtonRef.current;
      target?.focus();
    });
    return () => globalThis.cancelAnimationFrame(frame);
  }, [collapsed]);

  const selectedPet =
    getKolibriPet(petId);
  const currentMood =
    selectedPet.moods[moodIndex % selectedPet.moods.length];
  const panelPlacement =
    position.y > globalThis.innerHeight / 2 ? "above" : "below";
  const panelWidth = Math.max(
    0,
    Math.min(336, globalThis.innerWidth - 24),
  );
  const panelViewportLeft = Math.max(
    12,
    Math.min(
      position.x,
      globalThis.innerWidth - panelWidth - 12,
    ),
  );
  const panelLeft = panelViewportLeft - position.x;

  const toggleAssistant = () => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    setMoodIndex((current) => (current + 1) % selectedPet.moods.length);
    setActive(true);
    setAssistantOpen((current) => !current);
    if (activeTimerRef.current) clearTimeout(activeTimerRef.current);
    activeTimerRef.current = setTimeout(() => setActive(false), 900);
  };

  const setCollapsedPreference = (next: boolean) => {
    setCollapsed(next);
    const side =
      position.x + 66 < globalThis.innerWidth / 2 ? "left" : "right";
    if (next) setCollapsedSide(side);
    try {
      globalThis.localStorage.setItem(
        "kolibri.ui.pet-collapsed",
        String(next),
      );
      if (next) globalThis.localStorage.setItem("kolibri.ui.pet-side", side);
    } catch {
      // Keep the preference for the mounted application.
    }
  };

  const collapsePet = () => {
    pendingFocusRef.current = "restore";
    setAssistantOpen(false);
    setCollapsedPreference(true);
  };

  const restorePet = () => {
    pendingFocusRef.current = "collapse";
    setCollapsedPreference(false);
  };

  const persistPosition = (next: { x: number; y: number }) => {
    try {
      globalThis.localStorage.setItem(
        "kolibri.ui.pet-position",
        JSON.stringify(next),
      );
    } catch {
      // Keep the placement for the mounted application.
    }
  };

  const moveWithKeyboard = (deltaX: number, deltaY: number) => {
    const next = clampPetPosition({
      x: position.x + deltaX,
      y: position.y + deltaY,
    });
    setPosition(next);
    persistPosition(next);
  };

  if (!mounted) return null;

  if (collapsed) {
    return createPortal(
      <div
        data-slot="kolibri-pet"
        className={cn(
          "pointer-events-none fixed z-40 min-[960px]:z-[70]",
          collapsedSide === "left" ? "left-0" : "right-0",
          className,
        )}
        style={{
          top: Math.max(
            64,
            Math.min(globalThis.innerHeight - 64, position.y + 28),
          ),
        }}
      >
        <button
          ref={restoreButtonRef}
          type="button"
          onClick={restorePet}
          className={cn(
            "pointer-events-auto group flex h-11 items-center gap-1.5 border border-sky-200/70 bg-white/92 text-xs font-medium text-sky-900 shadow-lg outline-none transition hover:bg-sky-50 focus-visible:ring-2 focus-visible:ring-sky-400/60 dark:border-sky-900 dark:bg-sky-950/90 dark:text-sky-100",
            collapsedSide === "left"
              ? "rounded-r-xl border-l-0 pr-2 pl-1"
              : "flex-row-reverse rounded-l-xl border-r-0 pr-1 pl-2",
          )}
          aria-label={`Вернуть питомца ${selectedPet.name}`}
        >
          <PetAvatar id={petId} className="size-7" />
          Вернуть
        </button>
      </div>,
      globalThis.document.body,
    );
  }

  return createPortal(
    <div
      data-slot="kolibri-pet"
      data-pet-run-state={runState}
      className={cn(
        "pointer-events-none fixed z-40 flex w-[132px] flex-col items-center min-[960px]:z-[70]",
        className,
      )}
      style={{ left: position.x, top: position.y }}
    >
      <button
        ref={collapseButtonRef}
        type="button"
        onClick={collapsePet}
        className="group/collapse pointer-events-auto text-muted-foreground hover:text-foreground absolute -top-3 -right-3 z-10 flex size-11 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60"
        aria-label="Убрать питомца в сторону"
      >
        <span className="flex size-7 items-center justify-center rounded-full border border-sky-200/70 bg-white/90 shadow-sm transition group-hover/collapse:bg-sky-50 dark:border-sky-900 dark:bg-sky-950/90">
          <PanelRightOpen className="size-3.5" />
        </span>
      </button>
      <button
        ref={buttonRef}
        type="button"
        data-active={active ? "true" : undefined}
        data-pet-run-state={runState}
        className="pointer-events-auto group/pet relative flex h-[100px] w-[132px] touch-none cursor-grab items-center justify-center rounded-2xl outline-none transition-transform duration-200 hover:scale-[1.03] focus-visible:ring-2 focus-visible:ring-sky-400/60 active:cursor-grabbing active:scale-[1.01]"
        aria-describedby={PET_MOVEMENT_INSTRUCTIONS_ID}
        aria-controls={PET_ASSISTANT_PANEL_ID}
        aria-expanded={assistantOpen}
        aria-label={`Питомец ${selectedPet.name}. ${PET_RUN_COPY[runState]}. Нажмите, чтобы открыть помощника; перетащите в любую точку экрана.`}
        onClick={toggleAssistant}
        onKeyDown={(event) => {
          const step = event.shiftKey ? 32 : 12;
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            moveWithKeyboard(-step, 0);
          } else if (event.key === "ArrowRight") {
            event.preventDefault();
            moveWithKeyboard(step, 0);
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            moveWithKeyboard(0, -step);
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            moveWithKeyboard(0, step);
          }
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          dragRef.current = {
            originX: position.x,
            originY: position.y,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            moved: false,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const bounds = buttonRef.current?.getBoundingClientRect();
          if (!bounds) return;
          const x = (event.clientX - bounds.left) / bounds.width - 0.5;
          const y = (event.clientY - bounds.top) / bounds.height - 0.5;
          setGaze({
            x: Math.max(-1.8, Math.min(1.8, x * 3.6)),
            y: Math.max(-1.2, Math.min(1.2, y * 2.4)),
          });
          const drag = dragRef.current;
          if (!drag || drag.pointerId !== event.pointerId) return;
          const deltaX = event.clientX - drag.startX;
          const deltaY = event.clientY - drag.startY;
          if (Math.hypot(deltaX, deltaY) > 4) drag.moved = true;
          setPosition(
            clampPetPosition({
              x: drag.originX + deltaX,
              y: drag.originY + deltaY,
            }),
          );
        }}
        onPointerUp={(event) => {
          const drag = dragRef.current;
          if (!drag || drag.pointerId !== event.pointerId) return;
          const next = clampPetPosition({
            x: drag.originX + event.clientX - drag.startX,
            y: drag.originY + event.clientY - drag.startY,
          });
          suppressClickRef.current = drag.moved;
          dragRef.current = null;
          setPosition(next);
          persistPosition(next);
        }}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
        onPointerLeave={() => setGaze({ x: 0, y: 0 })}
      >
        <PetIllustration
          active={active}
          gaze={gaze}
          id={petId}
          reducedData={reducedData}
          reducedMotion={reducedMotion}
          state={runState}
        />
      </button>
      {assistantOpen ? (
        <PetMiniAssistant
          left={panelLeft}
          onClose={() => {
            setAssistantOpen(false);
            globalThis.requestAnimationFrame(() => buttonRef.current?.focus());
          }}
          pet={selectedPet}
          placement={panelPlacement}
          state={runState}
        />
      ) : null}
      <span
        aria-live="polite"
        className="pointer-events-none border-sky-200/70 bg-white/90 text-sky-900 -mt-1 rounded-full border px-2.5 py-1 text-[10px] font-medium shadow-md dark:border-sky-900 dark:bg-sky-950/90 dark:text-sky-100"
      >
        {selectedPet.name} ·{" "}
        {runState === "idle" ? currentMood : PET_RUN_COPY[runState]}
      </span>
      <span id={PET_MOVEMENT_INSTRUCTIONS_ID} className="sr-only">
        Клавиши со стрелками перемещают питомца. Shift + стрелка перемещает
        питомца на большой шаг.
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none text-muted-foreground mt-1 flex items-center gap-1 rounded-full bg-background/75 px-1.5 text-[9px]"
      >
        <ChevronsLeftRight className="size-2.5" />
        Стрелки · Shift — быстрее
      </span>
    </div>,
    globalThis.document.body,
  );
}

function clampPetPosition(position: { x: number; y: number }) {
  const viewportWidth =
    typeof globalThis.innerWidth === "number" ? globalThis.innerWidth : 1280;
  const viewportHeight =
    typeof globalThis.innerHeight === "number" ? globalThis.innerHeight : 800;
  return {
    x: Math.max(8, Math.min(viewportWidth - 140, position.x)),
    y: Math.max(56, Math.min(viewportHeight - 138, position.y)),
  };
}

function PetIllustration({
  active,
  compact = false,
  gaze,
  id,
  reducedData = false,
  reducedMotion = false,
  state = "idle",
}: {
  active: boolean;
  compact?: boolean;
  gaze: { x: number; y: number };
  id: KolibriPetId;
  reducedData?: boolean;
  reducedMotion?: boolean;
  state?: PetRunState;
}) {
  const pet = getKolibriPet(id);
  const useThumbnail = compact || reducedData;
  const artStyle = {
    "--pet-accent": pet.accent,
    "--pet-gaze-x": `${gaze.x}px`,
    "--pet-gaze-y": `${gaze.y}px`,
  } as CSSProperties;

  return (
    <span
      aria-hidden="true"
      data-active={active ? "true" : "false"}
      data-compact={compact ? "true" : "false"}
      data-pet-id={id}
      data-pet-run-state={state}
      data-reduced-motion={reducedMotion ? "true" : "false"}
      data-slot="kolibri-pet-art"
      className={cn(
        "kolibri-pet-art",
        compact ? "size-full" : "h-[94px] w-[132px]",
      )}
      style={artStyle}
    >
      <span className="kolibri-pet-art__idle">
        <span className="kolibri-pet-art__reaction">
          <img
            alt=""
            className="kolibri-pet-art__image"
            decoding="async"
            draggable={false}
            fetchPriority={useThumbnail ? "low" : "high"}
            height={useThumbnail ? 144 : 512}
            loading={useThumbnail ? "lazy" : "eager"}
            src={useThumbnail ? pet.thumbnail : pet.asset}
            width={useThumbnail ? 144 : 512}
          />
        </span>
      </span>
    </span>
  );
}

type NavigatorWithDataConnection = Navigator & {
  connection?: {
    addEventListener?: (type: "change", listener: () => void) => void;
    removeEventListener?: (type: "change", listener: () => void) => void;
    saveData?: boolean;
  };
};
