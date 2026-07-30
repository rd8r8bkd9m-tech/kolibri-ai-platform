import { useEffect, useState } from "react";
import { useColorScheme as useNativeColorScheme } from "react-native";

export function useColorScheme() {
  const [hydrated, setHydrated] = useState(false);
  const scheme = useNativeColorScheme();

  useEffect(() => setHydrated(true), []);
  return hydrated ? scheme : "light";
}
