import { useEffect, useState } from "react";
import { loadSupportedExecutionModes } from "../runtime/kolibriApi";

export function useExecutionModeSupport() {
  const [executionModes, setExecutionModes] = useState(["fast"]);

  useEffect(() => {
    const controller = new AbortController();
    loadSupportedExecutionModes(controller.signal)
      .then(setExecutionModes)
      .catch(() => setExecutionModes(["fast"]));
    return () => controller.abort();
  }, []);

  return executionModes;
}
