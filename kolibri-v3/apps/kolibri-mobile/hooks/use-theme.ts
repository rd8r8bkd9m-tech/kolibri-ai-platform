import { Colors } from "@/constants/theme";
import { useColorScheme } from "@/hooks/use-color-scheme";

export function useTheme() {
  const isDark = useColorScheme() === "dark";
  return {
    isDark,
    colors: isDark ? Colors.dark : Colors.light,
  };
}
