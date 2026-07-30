import { SymbolView } from "expo-symbols";

import {
  SF_SYMBOLS,
  type IconProps,
} from "@/components/ui/icon-mappings";

export function Icon({
  name,
  size = 24,
  color,
  weight = "regular",
}: IconProps) {
  return (
    <SymbolView
      name={SF_SYMBOLS[name]}
      tintColor={color}
      weight={weight}
      resizeMode="scaleAspectFit"
      style={{ height: size, width: size }}
    />
  );
}
