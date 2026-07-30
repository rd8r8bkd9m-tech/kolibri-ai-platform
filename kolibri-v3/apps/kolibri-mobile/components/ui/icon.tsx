import MaterialIcons from "@expo/vector-icons/MaterialIcons";

import {
  MATERIAL_ICONS,
  type IconProps,
} from "@/components/ui/icon-mappings";

export function Icon({ name, size = 24, color }: IconProps) {
  return (
    <MaterialIcons name={MATERIAL_ICONS[name]} size={size} color={color} />
  );
}
