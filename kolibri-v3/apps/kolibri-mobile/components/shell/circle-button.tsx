import type { PropsWithChildren } from "react";
import {
  Pressable,
  StyleSheet,
  type StyleProp,
  type PressableProps,
  type ViewStyle,
} from "react-native";

import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function CircleButton({
  children,
  style,
  ...props
}: PropsWithChildren<
  Omit<PressableProps, "style"> & { style?: StyleProp<ViewStyle> }
>) {
  const { colors } = useTheme();
  return (
    <Pressable
      {...props}
      hitSlop={4}
      style={({ pressed }) => [
        styles.root,
        { borderColor: colors.border },
        pressed && styles.pressed,
        style,
      ]}
    >
      {children}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: {
    alignItems: "center",
    borderRadius: Layout.headerControl / 2,
    borderWidth: StyleSheet.hairlineWidth,
    height: Layout.headerControl,
    justifyContent: "center",
    width: Layout.headerControl,
  },
  pressed: { opacity: 0.58 },
});
