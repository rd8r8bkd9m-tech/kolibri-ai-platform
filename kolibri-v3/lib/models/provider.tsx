"use client";

import { useIdentity } from "@/lib/identity/provider";
import {
  getModelCatalog,
  type ModelCatalog,
} from "@/lib/models/client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type ModelCatalogState = "idle" | "loading" | "ready" | "error";

type ModelCatalogContextValue = {
  state: ModelCatalogState;
  catalog: ModelCatalog | null;
  error: string | null;
  refresh: () => Promise<void>;
};

const ModelCatalogContext =
  createContext<ModelCatalogContextValue | null>(null);

export function ModelCatalogProvider({
  children,
}: Readonly<{ children: ReactNode }>) {
  const identity = useIdentity();
  const [state, setState] = useState<ModelCatalogState>("idle");
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestVersionRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    if (identity.status !== "authenticated") {
      setState("idle");
      setCatalog(null);
      setError(null);
      return;
    }
    setState("loading");
    try {
      const nextCatalog = await getModelCatalog();
      if (requestVersionRef.current !== requestVersion) return;
      setCatalog(nextCatalog);
      setState("ready");
      setError(null);
    } catch (requestError) {
      if (requestVersionRef.current !== requestVersion) return;
      setState("error");
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Каталог моделей сейчас недоступен.",
      );
    }
  }, [identity.status]);

  useEffect(() => {
    const requestVersion = ++requestVersionRef.current;
    if (identity.status !== "authenticated") {
      setState("idle");
      setCatalog(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setState("loading");
    void getModelCatalog(controller.signal)
      .then((next) => {
        if (requestVersionRef.current !== requestVersion) return;
        setCatalog(next);
        setState("ready");
        setError(null);
      })
      .catch((requestError: unknown) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        ) {
          return;
        }
        if (requestVersionRef.current !== requestVersion) return;
        setState("error");
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Каталог моделей сейчас недоступен.",
        );
      });
    return () => {
      controller.abort();
      if (requestVersionRef.current === requestVersion) {
        requestVersionRef.current += 1;
      }
    };
  }, [identity.status, identity.user?.id]);

  const value = useMemo<ModelCatalogContextValue>(
    () => ({ state, catalog, error, refresh }),
    [catalog, error, refresh, state],
  );

  return (
    <ModelCatalogContext.Provider value={value}>
      {children}
    </ModelCatalogContext.Provider>
  );
}

export function useModelCatalog() {
  const value = useContext(ModelCatalogContext);
  if (!value) {
    throw new Error(
      "useModelCatalog must be used inside ModelCatalogProvider.",
    );
  }
  return value;
}
