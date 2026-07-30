import {
  AuiIf,
  ComposerPrimitive,
  useAuiState,
} from "@assistant-ui/react-native";
import { Platform, Pressable, StyleSheet, View } from "react-native";

import { Icon } from "@/components/ui/icon";
import { Layout, Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

function SendButton() {
  const canSend = useAuiState((state) => state.composer.canSend);
  return (
    <ComposerPrimitive.Send
      accessibilityLabel="Отправить"
      onPressIn={() => canSend && haptics.success()}
      style={[
        styles.action,
        { backgroundColor: canSend ? "#0a84ff" : "#4b4b4b" },
      ]}
    >
      <Icon name="send" size={20} color="#ffffff" weight="semibold" />
    </ComposerPrimitive.Send>
  );
}

function StopButton() {
  return (
    <ComposerPrimitive.Cancel
      accessibilityLabel="Остановить ответ"
      onPressIn={haptics.light}
      style={[styles.action, { backgroundColor: "#0a84ff" }]}
    >
      <Icon name="stop" size={15} color="#ffffff" />
    </ComposerPrimitive.Cancel>
  );
}

export function Composer() {
  const { colors } = useTheme();
  return (
    <View style={styles.outer}>
      <ComposerPrimitive.Root
        style={[
          styles.root,
          { backgroundColor: colors.composer, borderColor: colors.border },
        ]}
      >
        <Pressable
          accessibilityHint="Вложения появятся после включения серверной загрузки"
          accessibilityLabel="Добавить вложение"
          accessibilityRole="button"
          accessibilityState={{ disabled: true }}
          disabled
          style={styles.plus}
        >
          <Icon name="plus" size={28} color={colors.foreground} />
        </Pressable>
        <ComposerPrimitive.Input
          accessibilityLabel="Сообщение"
          maxLength={65_536}
          multiline
          placeholder="Спросить Kolibri…"
          placeholderTextColor={colors.mutedForeground}
          style={[styles.input, { color: colors.foreground }]}
        />
        <AuiIf condition={(state) => !state.thread.isRunning}>
          <SendButton />
        </AuiIf>
        <AuiIf condition={(state) => state.thread.isRunning}>
          <StopButton />
        </AuiIf>
      </ComposerPrimitive.Root>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    alignSelf: "center",
    maxWidth: Layout.threadMaxWidth + 24,
    paddingHorizontal: Layout.edgeInset,
    paddingTop: 8,
    width: "100%",
  },
  root: {
    alignItems: "flex-end",
    borderRadius: Radius.composer,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    minHeight: 54,
    padding: 6,
  },
  plus: {
    alignItems: "center",
    height: 40,
    justifyContent: "center",
    opacity: 0.94,
    width: 40,
  },
  input: {
    flex: 1,
    fontSize: 16,
    lineHeight: 22,
    maxHeight: 132,
    minHeight: 40,
    paddingBottom: 9,
    paddingHorizontal: 7,
    paddingTop: 9,
    ...Platform.select({
      web: { outlineStyle: "none" } as never,
      default: {},
    }),
  },
  action: {
    alignItems: "center",
    borderRadius: 21,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
});
