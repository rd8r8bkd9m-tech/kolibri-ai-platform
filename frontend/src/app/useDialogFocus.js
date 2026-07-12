import { useEffect, useRef } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[contenteditable='true']",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

const focusLayers = [];

function canRestoreFocus(element) {
  return Boolean(
    element?.isConnected
    && !element.disabled
    && element.matches?.(FOCUSABLE)
    && !element.closest?.("[inert], [aria-hidden='true']"),
  );
}

export function useDialogFocus(dialogRef, {
  open = true,
  onEscape,
  initialFocus = "[data-dialog-initial-focus]",
  fallbackFocus = "",
} = {}) {
  const onEscapeRef = useRef(onEscape);
  useEffect(() => {
    onEscapeRef.current = onEscape;
  }, [onEscape]);

  useEffect(() => {
    if (!open) return undefined;
    const dialog = dialogRef.current;
    const document = globalThis.document;
    if (!dialog || !document) return undefined;
    const previouslyFocused = document.activeElement;
    const layer = Symbol("dialog-focus-layer");
    focusLayers.push(layer);
    const requestFrame = globalThis.requestAnimationFrame || ((callback) => globalThis.setTimeout(callback, 0));
    const cancelFrame = globalThis.cancelAnimationFrame || globalThis.clearTimeout;
    const focusFrame = requestFrame(() => {
      const target = dialog.querySelector(initialFocus) || dialog.querySelector(FOCUSABLE);
      target?.focus();
    });

    const onKeyDown = (event) => {
      if (focusLayers.at(-1) !== layer) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        onEscapeRef.current?.();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...dialog.querySelectorAll(FOCUSABLE)]
        .filter((element) => (
          !element.hasAttribute("disabled")
          && element.getAttribute("aria-hidden") !== "true"
          && element.getClientRects().length > 0
        ));
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    globalThis.addEventListener("keydown", onKeyDown);
    return () => {
      cancelFrame(focusFrame);
      globalThis.removeEventListener("keydown", onKeyDown);
      const layerIndex = focusLayers.lastIndexOf(layer);
      if (layerIndex >= 0) focusLayers.splice(layerIndex, 1);
      requestFrame(() => {
        if (canRestoreFocus(previouslyFocused)) previouslyFocused.focus();
        else if (fallbackFocus) document.querySelector(fallbackFocus)?.focus();
      });
    };
  }, [dialogRef, fallbackFocus, initialFocus, open]);
}
