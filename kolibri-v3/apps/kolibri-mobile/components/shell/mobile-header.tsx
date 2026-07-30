import { useAui } from "@assistant-ui/react-native";
import { useNavigation } from "expo-router";
import type { DrawerNavigationProp } from "expo-router/build/react-navigation/drawer/types";
import { StyleSheet, Text, View } from "react-native";

import { CircleButton } from "@/components/shell/circle-button";
import { HamburgerMark } from "@/components/shell/hamburger-mark";
import { Icon } from "@/components/ui/icon";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

export function MobileHeader() {
  const navigation =
    useNavigation<DrawerNavigationProp<{ index: undefined }, "index">>();
  const aui = useAui();
  const { colors } = useTheme();

  return (
    <View style={styles.root}>
      <CircleButton
        accessibilityLabel="Открыть меню"
        accessibilityRole="button"
        onPress={() => {
          haptics.selection();
          navigation.openDrawer();
        }}
      >
        <HamburgerMark />
      </CircleButton>

      <View accessibilityRole="header" style={styles.titleWrap}>
        <Text style={[styles.title, { color: colors.foreground }]}>Chat</Text>
        <View
          accessibilityElementsHidden
          style={[styles.underline, { backgroundColor: colors.foreground }]}
        />
      </View>

      <CircleButton
        accessibilityLabel="Новая задача"
        accessibilityRole="button"
        onPress={() => {
          haptics.selection();
          aui.threads.switchToNewThread();
        }}
      >
        <Icon name="bubble" size={26} color={colors.foreground} />
      </CircleButton>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    alignItems: "center",
    flexDirection: "row",
    height: 76,
    justifyContent: "space-between",
    paddingHorizontal: Layout.edgeInset,
  },
  titleWrap: { alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "700", letterSpacing: -0.5 },
  underline: { borderRadius: 2, height: 2, marginTop: 1, width: 44 },
});
