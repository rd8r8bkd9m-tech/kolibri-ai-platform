import {
  ThreadListItemByIndexProvider,
  ThreadListPrimitive,
  useAui,
} from "@assistant-ui/react-native";
import type { DrawerContentComponentProps } from "expo-router/build/react-navigation/drawer/types";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { HamburgerMark } from "@/components/shell/hamburger-mark";
import { Icon } from "@/components/ui/icon";
import { ThreadListItem } from "@/components/thread-list/thread-list-item";
import { Layout, Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { useMobileSession } from "@/src/auth/mobile-session";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";

export function DrawerContent({
  navigation,
}: DrawerContentComponentProps) {
  const session = useMobileSession();
  const aui = useAui();
  const { colors } = useTheme();
  const estimateAccess = constructionEstimateAccess(session.user);

  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      <View style={styles.top}>
        <Pressable
          accessibilityLabel="Закрыть меню"
          accessibilityRole="button"
          onPress={() => navigation.closeDrawer()}
          style={({ pressed }) => [
            styles.menuButton,
            { borderColor: colors.border },
            pressed && styles.pressed,
          ]}
        >
          <HamburgerMark />
        </Pressable>
        <Text style={[styles.brand, { color: colors.foreground }]}>
          Kolibri AI
        </Text>
      </View>

      <ThreadListPrimitive.Root style={styles.threadRoot}>
        <Pressable
          accessibilityLabel="Новая задача"
          accessibilityRole="button"
          onPress={() => {
            haptics.selection();
            aui.threads.switchToNewThread();
            navigation.closeDrawer();
          }}
          style={({ pressed }) => [
            styles.newTask,
            {
              backgroundColor: pressed ? colors.muted : colors.surface,
            },
          ]}
        >
          <Icon name="compose" size={21} color={colors.foreground} />
          <Text style={[styles.newTaskText, { color: colors.foreground }]}>
            Новая задача
          </Text>
        </Pressable>

        <Text style={[styles.section, { color: colors.mutedForeground }]}>
          Недавние
        </Text>
        <ThreadListPrimitive.Items
          contentContainerStyle={styles.listContent}
          renderItem={({ index }) => (
            <ThreadListItemByIndexProvider index={index} archived={false}>
              <ThreadListItem onSelect={() => navigation.closeDrawer()} />
            </ThreadListItemByIndexProvider>
          )}
          showsVerticalScrollIndicator={false}
          style={styles.list}
        />
        <Text style={[styles.section, { color: colors.mutedForeground }]}>
          Инструменты
        </Text>
        <Pressable
          accessibilityHint={
            estimateAccess.enabled ? undefined : estimateAccess.reason
          }
          accessibilityLabel="Сметы"
          accessibilityRole="button"
          accessibilityState={{ disabled: !estimateAccess.enabled }}
          disabled={!estimateAccess.enabled}
          onPress={() => {
            haptics.selection();
            navigation.navigate("estimates");
          }}
          style={({ pressed }) => [
            styles.verticalEntry,
            {
              backgroundColor: colors.surface,
              opacity: estimateAccess.enabled ? 1 : 0.48,
            },
            pressed && styles.pressed,
          ]}
        >
          <Icon name="document" size={21} color={colors.foreground} />
          <View style={styles.verticalEntryCopy}>
            <Text
              style={[styles.verticalEntryText, { color: colors.foreground }]}
            >
              Сметы
            </Text>
            {!estimateAccess.enabled ? (
              <Text
                numberOfLines={1}
                style={[
                  styles.verticalEntryHint,
                  { color: colors.mutedForeground },
                ]}
              >
                Ожидает entitlement
              </Text>
            ) : null}
          </View>
          <Icon
            name="chevron-right"
            size={18}
            color={colors.mutedForeground}
          />
        </Pressable>
      </ThreadListPrimitive.Root>

      <View style={[styles.account, { borderTopColor: colors.muted }]}>
        <View
          style={[styles.avatar, { backgroundColor: colors.foreground }]}
        >
          <Text
            style={[styles.avatarText, { color: colors.primaryForeground }]}
          >
            {session.user?.name.trim().slice(0, 1).toUpperCase() ?? "K"}
          </Text>
        </View>
        <View style={styles.accountCopy}>
          <Text
            numberOfLines={1}
            style={[styles.accountName, { color: colors.foreground }]}
          >
            {session.user?.name ?? "Kolibri"}
          </Text>
          <Text
            numberOfLines={1}
            style={[styles.accountEmail, { color: colors.mutedForeground }]}
          >
            {session.user?.email}
          </Text>
        </View>
        <Pressable
          accessibilityLabel="Выйти"
          accessibilityRole="button"
          hitSlop={8}
          onPress={() => {
            haptics.selection();
            void session.logout();
          }}
          style={({ pressed }) => [styles.logout, pressed && styles.pressed]}
        >
          <Icon name="logout" size={22} color={colors.mutedForeground} />
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  top: {
    alignItems: "center",
    flexDirection: "row",
    gap: 13,
    height: 76,
    paddingHorizontal: Layout.edgeInset,
  },
  menuButton: {
    alignItems: "center",
    borderRadius: Layout.headerControl / 2,
    borderWidth: StyleSheet.hairlineWidth,
    height: Layout.headerControl,
    justifyContent: "center",
    width: Layout.headerControl,
  },
  brand: { fontSize: 23, fontWeight: "700", letterSpacing: -0.5 },
  threadRoot: { flex: 1 },
  newTask: {
    alignItems: "center",
    borderRadius: Radius.circle,
    flexDirection: "row",
    gap: 11,
    height: 50,
    marginHorizontal: 12,
    paddingHorizontal: 17,
  },
  newTaskText: { fontSize: 16, fontWeight: "600" },
  section: {
    fontSize: 14,
    fontWeight: "600",
    paddingBottom: 7,
    paddingHorizontal: 20,
    paddingTop: 23,
  },
  list: { flex: 1 },
  listContent: { paddingBottom: 12 },
  verticalEntry: {
    alignItems: "center",
    borderRadius: Radius.card,
    flexDirection: "row",
    marginBottom: 12,
    marginHorizontal: 12,
    minHeight: 54,
    paddingHorizontal: 15,
  },
  verticalEntryCopy: { flex: 1, marginLeft: 11 },
  verticalEntryText: { fontSize: 15, fontWeight: "700" },
  verticalEntryHint: { fontSize: 11, marginTop: 2 },
  account: {
    alignItems: "center",
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    minHeight: 74,
    paddingHorizontal: 16,
  },
  avatar: {
    alignItems: "center",
    borderRadius: 18,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  avatarText: { fontSize: 16, fontWeight: "700" },
  accountCopy: { flex: 1, marginLeft: 11 },
  accountName: { fontSize: 15, fontWeight: "600" },
  accountEmail: { fontSize: 12, marginTop: 2 },
  logout: {
    alignItems: "center",
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  pressed: { opacity: 0.56 },
});
