"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export const KOLIBRI_THEME_STORAGE_KEY = "kolibri-theme";

export type KolibriThemePreference = "system" | "light" | "dark";

type KolibriThemeContextValue = {
  preference: KolibriThemePreference;
  resolvedTheme: "light" | "dark";
  setPreference: (preference: KolibriThemePreference) => void;
};

const KolibriThemeContext = createContext<KolibriThemeContextValue | null>(
  null,
);

function isThemePreference(value: unknown): value is KolibriThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

function systemTheme(): "light" | "dark" {
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(preference: KolibriThemePreference) {
  const resolved = preference === "system" ? systemTheme() : preference;
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  return resolved;
}

export function KolibriThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setStoredPreference] =
    useState<KolibriThemePreference>("system");
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(
    "light",
  );

  const setPreference = useCallback((next: KolibriThemePreference) => {
    setStoredPreference(next);
    setResolvedTheme(applyTheme(next));
    try {
      globalThis.localStorage.setItem(KOLIBRI_THEME_STORAGE_KEY, next);
    } catch {
      // A blocked storage API must not prevent theme changes in this session.
    }
  }, []);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = globalThis.localStorage.getItem(KOLIBRI_THEME_STORAGE_KEY);
    } catch {
      // Keep the bounded system default when storage is unavailable.
    }
    const initialPreference = isThemePreference(stored) ? stored : "system";
    setStoredPreference(initialPreference);
  }, []);

  useEffect(() => {
    setResolvedTheme(applyTheme(preference));
    const media = globalThis.matchMedia("(prefers-color-scheme: dark)");
    const syncSystemTheme = () => {
      if (preference === "system") {
        setResolvedTheme(applyTheme("system"));
      }
    };
    media.addEventListener("change", syncSystemTheme);
    return () => media.removeEventListener("change", syncSystemTheme);
  }, [preference]);

  const value = useMemo(
    () => ({ preference, resolvedTheme, setPreference }),
    [preference, resolvedTheme, setPreference],
  );

  return (
    <KolibriThemeContext.Provider value={value}>
      {children}
    </KolibriThemeContext.Provider>
  );
}

export function useKolibriTheme() {
  const context = useContext(KolibriThemeContext);
  if (!context) {
    throw new Error(
      "useKolibriTheme must be used inside KolibriThemeProvider.",
    );
  }
  return context;
}
