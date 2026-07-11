import { useEffect, useState } from "react";
import { loadSupportedExecutionModes } from "../runtime/kolibriApi";

export function useExecutionModeSupport() {
  const [executionModes, setExecutionModes] = useState(["fast"]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    loadSupportedExecutionModes(controller.signal)
      .then((modes) => {
        if (active) setExecutionModes(modes);
      })
      .catch((error) => {
        if (active && error?.name !== "AbortError") setExecutionModes(["fast"]);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return executionModes;
}
