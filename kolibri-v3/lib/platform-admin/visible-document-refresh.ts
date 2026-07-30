"use client";

import { useEffect, useRef } from "react";

const MINIMUM_REFRESH_MS = 5_000;
const MAXIMUM_REFRESH_MS = 60_000;
export const PLATFORM_ADMIN_LIVE_REFRESH_MS = 10_000;

export function mergeBoundedFirstPage<T>(
  current: T[],
  incoming: T[],
  keyOf: (item: T) => string,
) {
  const maximumItems = Math.max(current.length, incoming.length);
  if (maximumItems === 0) return [];
  const merged = new Map<string, T>();
  for (const item of incoming) merged.set(keyOf(item), item);
  for (const item of current) {
    const key = keyOf(item);
    if (!merged.has(key)) merged.set(key, item);
  }
  return [...merged.values()].slice(0, maximumItems);
}

export function useVisibleDocumentRefresh(
  refresh: (signal: AbortSignal) => Promise<void>,
  intervalMs = PLATFORM_ADMIN_LIVE_REFRESH_MS,
) {
  const refreshRef = useRef(refresh);

  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    const boundedInterval = Math.min(
      MAXIMUM_REFRESH_MS,
      Math.max(MINIMUM_REFRESH_MS, intervalMs),
    );
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let activeController: AbortController | null = null;

    const clearTimer = () => {
      if (timer === null) return;
      clearTimeout(timer);
      timer = null;
    };

    const schedule = () => {
      if (
        stopped ||
        timer !== null ||
        document.visibilityState !== "visible"
      ) {
        return;
      }
      timer = setTimeout(() => {
        timer = null;
        void execute();
      }, boundedInterval);
    };

    const execute = async () => {
      if (stopped || document.visibilityState !== "visible") return;
      if (activeController) {
        schedule();
        return;
      }
      const controller = new AbortController();
      activeController = controller;
      try {
        await refreshRef.current(controller.signal);
      } catch {
        // The refresh callback owns its quiet, in-panel error state.
      } finally {
        if (activeController === controller) activeController = null;
        schedule();
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") {
        clearTimer();
        activeController?.abort();
        return;
      }
      void execute();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    schedule();
    return () => {
      stopped = true;
      clearTimer();
      activeController?.abort();
      document.removeEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
    };
  }, [intervalMs]);
}
