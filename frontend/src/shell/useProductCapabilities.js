import { useEffect, useMemo, useState } from "react";
import { availableTools } from "../app/toolAvailability";
import { loadPublicCapabilities } from "../runtime/kolibriApi";

export function useProductCapabilities() {
  const [capabilities, setCapabilities] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const refresh = () => loadPublicCapabilities(controller.signal)
      .then((records) => {
        if (active) setCapabilities(Array.isArray(records) ? records : []);
      })
      .catch((error) => {
        if (active && error?.name !== "AbortError") setCapabilities([]);
      });
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
      controller.abort();
    };
  }, []);

  return useMemo(() => ({
    capabilities,
    tools: availableTools(capabilities),
  }), [capabilities]);
}
