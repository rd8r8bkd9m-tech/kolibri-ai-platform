import {
  ThreadListItemPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react-native";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/components/ui/icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

export function ThreadListItem({ onSelect }: { onSelect: () => void }) {
  const aui = useAui();
  const { colors } = useTheme();
  const item = useAuiState((state) => state.threadListItem);
  const active = useAuiState(
    (state) => state.threads.mainThreadId === state.threadListItem.id,
  );
  const pinned = item.custom?.pinned === true;
  const draft = item.custom?.draft === true;

  const menu = () => {
    if (draft) return;
    haptics.light();
    Alert.alert(item.title || "Задача", undefined, [
      {
        text: pinned ? "Открепить" : "Закрепить",
        onPress: () =>
          void aui.threadListItem.updateCustom({
            ...item.custom,
            pinned: !pinned,
          }),
      },
      {
        text: "Архивировать",
        onPress: () => void aui.threadListItem.archive(),
      },
      {
        text: "Удалить из списка",
        style: "destructive",
        onPress: () => void aui.threadListItem.delete(),
      },
      { text: "Отмена", style: "cancel" },
    ]);
  };

  return (
    <ThreadListItemPrimitive.Root>
      <Pressable
        accessibilityHint="Удерживайте для действий"
        accessibilityRole="button"
        onLongPress={menu}
        onPress={() => {
          haptics.selection();
          void aui.threadListItem.switchTo();
          onSelect();
        }}
        style={({ pressed }) => [
          styles.row,
          (active || pressed) && { backgroundColor: colors.muted },
        ]}
      >
        <View style={styles.icon}>
          <Icon
            name={pinned ? "pin" : "bubble"}
            size={18}
            color={colors.foreground}
          />
        </View>
        <Text
          numberOfLines={1}
          style={[
            styles.title,
            {
              color: colors.foreground,
              fontWeight: active ? "600" : "500",
            },
          ]}
        >
          <ThreadListItemPrimitive.Title fallback="Новая задача" />
        </Text>
      </Pressable>
    </ThreadListItemPrimitive.Root>
  );
}

const styles = StyleSheet.create({
  row: {
    alignItems: "center",
    borderRadius: Radius.md,
    flexDirection: "row",
    gap: 11,
    marginHorizontal: 8,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  icon: { alignItems: "center", justifyContent: "center", width: 22 },
  title: { flex: 1, fontSize: 16, letterSpacing: -0.2 },
});
