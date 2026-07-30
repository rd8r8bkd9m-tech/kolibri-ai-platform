export type CoreDestination = "chat" | "projects" | "library" | "settings";

export type CoreNavigationRegistration = {
  owner: "core";
  id: CoreDestination;
  label: string;
};

/**
 * Core contains only universal destinations. Vertical registrations live in
 * `src/verticals` and are composed at the release boundary.
 */
export const CORE_NAVIGATION: readonly CoreNavigationRegistration[] = [
  { owner: "core", id: "chat", label: "Чат" },
  { owner: "core", id: "projects", label: "Проекты" },
  { owner: "core", id: "library", label: "Библиотека" },
  { owner: "core", id: "settings", label: "Настройки" },
] as const;

export const availableCoreNavigation = () => CORE_NAVIGATION;
