import {
  ErrorPrimitive,
  MessagePrimitive,
  useAuiState,
  type TextMessagePartComponent,
} from "@assistant-ui/react-native";
import { useEffect, useState } from "react";
import {
  Animated,
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { MessageActionBar } from "@/components/assistant-ui/message-action-bar";
import { MessageBranchPicker } from "@/components/assistant-ui/message-branch-picker";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

const UserText: TextMessagePartComponent = ({ text }) => {
  const { colors } = useTheme();
  return <Text style={[styles.userText, { color: colors.foreground }]}>{text}</Text>;
};

const AssistantText: TextMessagePartComponent = ({ text }) => {
  const { colors } = useTheme();
  return (
    <Text selectable style={[styles.assistantText, { color: colors.foreground }]}>
      {text}
    </Text>
  );
};

function TypingDot({ delay }: { delay: number }) {
  const { colors } = useTheme();
  const [opacity] = useState(() => new Animated.Value(0.28));

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 1,
          duration: 380,
          delay,
          useNativeDriver: Platform.OS !== "web",
        }),
        Animated.timing(opacity, {
          toValue: 0.28,
          duration: 380,
          useNativeDriver: Platform.OS !== "web",
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [delay, opacity]);

  return (
    <Animated.View
      style={[styles.dot, { backgroundColor: colors.mutedForeground, opacity }]}
    />
  );
}

function TypingIndicator() {
  const running = useAuiState(
    (state) => state.message.status?.type === "running",
  );
  if (!running) return null;
  return (
    <View accessibilityLabel="Kolibri формирует ответ" style={styles.typing}>
      <TypingDot delay={0} />
      <TypingDot delay={140} />
      <TypingDot delay={280} />
    </View>
  );
}

function UserMessage() {
  const { colors } = useTheme();
  return (
    <MessagePrimitive.Root style={styles.userRoot}>
      <View style={[styles.userBubble, { backgroundColor: colors.muted }]}>
        <MessagePrimitive.Parts components={{ Text: UserText }} />
      </View>
      <MessageBranchPicker align="flex-end" />
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const { colors } = useTheme();
  return (
    <MessagePrimitive.Root style={styles.assistantRoot}>
      <View style={styles.assistantContent}>
        <MessagePrimitive.Parts
          components={{ Text: AssistantText, Empty: TypingIndicator }}
        />
        <ErrorPrimitive.Root
          style={[
            styles.error,
            {
              backgroundColor: colors.destructiveSurface,
              borderColor: colors.destructive,
            },
          ]}
        >
          <ErrorPrimitive.Message
            style={[styles.errorText, { color: colors.destructive }]}
          />
        </ErrorPrimitive.Root>
      </View>
      <MessagePrimitive.If running={false}>
        <View style={styles.actions}>
          <MessageBranchPicker />
          <MessageActionBar />
        </View>
      </MessagePrimitive.If>
    </MessagePrimitive.Root>
  );
}

export function MessageBubble() {
  const role = useAuiState((state) => state.message.role);
  return role === "user" ? <UserMessage /> : <AssistantMessage />;
}

const styles = StyleSheet.create({
  userRoot: { alignItems: "flex-end" },
  userBubble: {
    borderRadius: Radius.bubble,
    maxWidth: "86%",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  assistantRoot: { alignItems: "flex-start" },
  assistantContent: { paddingHorizontal: 2 },
  userText: { fontSize: 16, letterSpacing: -0.2, lineHeight: 22 },
  assistantText: { fontSize: 16, letterSpacing: -0.2, lineHeight: 25 },
  typing: {
    alignItems: "center",
    flexDirection: "row",
    gap: 5,
    paddingVertical: 9,
  },
  dot: { borderRadius: 3.5, height: 7, width: 7 },
  actions: {
    alignItems: "center",
    flexDirection: "row",
    gap: 4,
    marginLeft: -4,
    marginTop: 6,
  },
  error: {
    borderRadius: Radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    marginTop: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  errorText: { fontSize: 14, lineHeight: 20 },
});
