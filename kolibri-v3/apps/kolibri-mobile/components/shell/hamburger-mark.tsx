import { StyleSheet, View } from "react-native";

import { useTheme } from "@/hooks/use-theme";

export function HamburgerMark() {
  const { colors } = useTheme();
  return (
    <View accessibilityElementsHidden importantForAccessibility="no" style={styles.mark}>
      <View style={[styles.line, { backgroundColor: colors.foreground }]} />
      <View style={[styles.line, { backgroundColor: colors.foreground }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  mark: { gap: 7.5 },
  line: { borderRadius: 2, height: 2.5, width: 26 },
});
