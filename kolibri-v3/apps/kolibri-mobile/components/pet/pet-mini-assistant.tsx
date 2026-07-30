import {
  ComposerPrimitive,
  useAuiState,
} from "@assistant-ui/react-native";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  BackHandler,
  Image,
  Keyboard,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";

import { Icon } from "@/components/ui/icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import {
  DEFAULT_NATIVE_PET,
  NATIVE_PETS,
  type NativePetDefinition,
} from "@/src/pets/registry";
import {
  getNativePet,
  persistNativePetId,
  readNativePetId,
} from "@/src/pets/selection";

type PetRunState = "idle" | "thinking" | "success" | "error";

const runCopy: Record<PetRunState, string> = {
  idle: "Готов помочь в этом чате",
  thinking: "Работаю над ответом…",
  success: "Ответ готов",
  error: "Не удалось завершить ответ",
};

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

function usePetRunState(): PetRunState {
  return useAuiState((state) => {
    if (state.thread.isRunning) return "thinking";
    const last = state.thread.messages.at(-1);
    if (!last || last.role !== "assistant") return "idle";
    if (last.status.type === "complete") return "success";
    if (last.status.type === "incomplete") {
      return last.status.reason === "cancelled" ? "idle" : "error";
    }
    return "idle";
  });
}

function PetStatus({
  accent,
  state,
}: {
  accent: string;
  state: PetRunState;
}) {
  const { colors } = useTheme();
  const color =
    state === "error"
      ? colors.destructive
      : state === "success"
        ? colors.success
        : state === "thinking"
          ? accent
          : colors.mutedForeground;

  return (
    <View accessibilityLiveRegion="polite" style={styles.statusRow}>
      <View
        accessibilityElementsHidden
        style={[styles.statusDot, { backgroundColor: color }]}
      />
      <Text style={[styles.statusText, { color: colors.mutedForeground }]}>
        {runCopy[state]}
      </Text>
    </View>
  );
}

function PetPicker({
  selected,
  onSelect,
}: {
  selected: NativePetDefinition;
  onSelect: (pet: NativePetDefinition) => void;
}) {
  const { colors } = useTheme();
  return (
    <ScrollView
      accessibilityLabel="Выбор помощника"
      contentContainerStyle={styles.pickerContent}
      horizontal
      keyboardShouldPersistTaps="handled"
      showsHorizontalScrollIndicator={false}
      style={styles.picker}
    >
      {NATIVE_PETS.map((pet) => {
        const active = selected.id === pet.id;
        return (
          <Pressable
            accessibilityLabel={`${pet.name}, ${pet.role}`}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            key={pet.id}
            onPress={() => {
              haptics.selection();
              onSelect(pet);
            }}
            style={({ pressed }) => [
              styles.petChoice,
              {
                backgroundColor: active ? colors.muted : colors.surface,
                borderColor: active ? pet.accent : "transparent",
              },
              pressed && styles.pressed,
            ]}
          >
            <Image source={pet.thumbnail} style={styles.petChoiceImage} />
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function PetComposer({
  accent,
}: {
  accent: string;
}) {
  const canSend = useAuiState((state) => state.composer.canSend);
  const running = useAuiState((state) => state.thread.isRunning);
  const { colors } = useTheme();

  return (
    <ComposerPrimitive.Root
      style={[
        styles.composer,
        { backgroundColor: colors.composer, borderColor: colors.border },
      ]}
    >
      <ComposerPrimitive.Input
        accessibilityLabel="Сообщение питомцу в текущий чат"
        autoFocus
        maxLength={65_536}
        multiline
        placeholder="Написать в этот чат…"
        placeholderTextColor={colors.mutedForeground}
        style={[styles.input, { color: colors.foreground }]}
        submitMode="none"
      />
      {running ? (
        <ComposerPrimitive.Cancel
          accessibilityLabel="Остановить ответ"
          onPressIn={haptics.light}
          style={[styles.send, { backgroundColor: accent }]}
        >
          <Icon name="stop" color="#ffffff" size={14} />
        </ComposerPrimitive.Cancel>
      ) : (
        <ComposerPrimitive.Send
          accessibilityLabel="Отправить в текущий чат"
          accessibilityState={{ disabled: !canSend }}
          onPressIn={() => canSend && haptics.success()}
          style={[
            styles.send,
            {
              backgroundColor: canSend ? accent : colors.muted,
              opacity: canSend ? 1 : 0.72,
            },
          ]}
        >
          <Icon
            name="send"
            color={canSend ? "#ffffff" : colors.mutedForeground}
            size={18}
            weight="semibold"
          />
        </ComposerPrimitive.Send>
      )}
    </ComposerPrimitive.Root>
  );
}

export function PetMiniAssistant() {
  const [open, setOpen] = useState(false);
  const [pet, setPet] = useState<NativePetDefinition>(DEFAULT_NATIVE_PET);
  const state = usePetRunState();
  const previousState = useRef<PetRunState>(state);
  const reduceMotion = useReducedMotion();
  const { colors } = useTheme();
  const reveal = useSharedValue(0);
  const bob = useSharedValue(0);

  useEffect(() => {
    let active = true;
    void readNativePetId().then((id) => {
      if (active) setPet(getNativePet(id));
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    reveal.value = withTiming(open ? 1 : 0, {
      duration: reduceMotion ? 0 : 180,
      easing: Easing.out(Easing.cubic),
    });
  }, [open, reduceMotion, reveal]);

  useEffect(() => {
    if (reduceMotion) {
      bob.value = 0;
      return;
    }
    const distance =
      state === "thinking" ? -8 : state === "success" ? -6 : -4;
    const duration =
      state === "thinking" ? 620 : state === "error" ? 380 : 1_300;
    bob.value = withRepeat(
      withTiming(distance, {
        duration,
        easing: Easing.inOut(Easing.sin),
      }),
      -1,
      true,
    );
  }, [bob, reduceMotion, state]);

  useEffect(() => {
    if (previousState.current === "thinking" && state === "success") {
      haptics.success();
    } else if (
      previousState.current === "thinking" &&
      state === "error"
    ) {
      haptics.error();
    }
    previousState.current = state;
  }, [state]);

  useEffect(() => {
    if (!open || Platform.OS !== "android") return;
    const subscription = BackHandler.addEventListener(
      "hardwareBackPress",
      () => {
        Keyboard.dismiss();
        setOpen(false);
        return true;
      },
    );
    return () => subscription.remove();
  }, [open]);

  const triggerStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: bob.value }],
  }));
  const panelStyle = useAnimatedStyle(() => ({
    opacity: reveal.value,
    transform: [
      { translateY: (1 - reveal.value) * 12 },
      { scale: 0.98 + reveal.value * 0.02 },
    ],
  }));
  const panelPointerEvents = useMemo(() => (open ? "auto" : "none"), [open]);

  return (
    <View pointerEvents="box-none" style={StyleSheet.absoluteFill}>
      <AnimatedPressable
        accessibilityHint="Открывает компактное поле того же текущего чата"
        accessibilityLabel={`${pet.name}, мобильный помощник`}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityValue={{ text: runCopy[state] }}
        onPress={() => {
          haptics.selection();
          setOpen((current) => !current);
        }}
        style={[
          styles.trigger,
          {
            backgroundColor: colors.surfaceRaised,
            borderColor: pet.accent,
          },
          triggerStyle,
        ]}
      >
        <Image source={pet.active} style={styles.triggerImage} />
        <View
          accessibilityElementsHidden
          style={[
            styles.triggerStatus,
            {
              backgroundColor:
                state === "error"
                  ? colors.destructive
                  : state === "thinking"
                    ? pet.accent
                    : state === "success"
                      ? colors.success
                      : colors.mutedForeground,
            },
          ]}
        />
      </AnimatedPressable>

      <Animated.View
        accessibilityViewIsModal={open}
        pointerEvents={panelPointerEvents}
        style={[
          styles.panel,
          {
            backgroundColor: colors.surfaceRaised,
            borderColor: colors.border,
          },
          panelStyle,
        ]}
      >
        <View style={styles.panelHeader}>
          <Image source={pet.active} style={styles.panelPet} />
          <View style={styles.identity}>
            <Text style={[styles.petName, { color: colors.foreground }]}>
              {pet.name}
            </Text>
            <Text
              numberOfLines={1}
              style={[styles.petRole, { color: colors.mutedForeground }]}
            >
              {pet.role} · {pet.personality}
            </Text>
          </View>
          <Pressable
            accessibilityLabel="Закрыть помощника"
            accessibilityRole="button"
            hitSlop={8}
            onPress={() => {
              Keyboard.dismiss();
              haptics.light();
              setOpen(false);
            }}
            style={({ pressed }) => [
              styles.close,
              { backgroundColor: colors.muted },
              pressed && styles.pressed,
            ]}
          >
            <Icon name="close" color={colors.foreground} size={18} />
          </Pressable>
        </View>
        <PetStatus accent={pet.accent} state={state} />
        <PetPicker
          selected={pet}
          onSelect={(nextPet) => {
            setPet(nextPet);
            void persistNativePetId(nextPet.id);
          }}
        />
        <PetComposer accent={pet.accent} />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  trigger: {
    alignItems: "center",
    borderRadius: 31,
    borderWidth: 1.5,
    bottom: 70,
    height: 62,
    justifyContent: "center",
    position: "absolute",
    right: 16,
    shadowColor: "#000000",
    shadowOffset: { height: 5, width: 0 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    width: 62,
    zIndex: 20,
  },
  triggerImage: { height: 60, resizeMode: "contain", width: 60 },
  triggerStatus: {
    borderColor: "#ffffff",
    borderRadius: 6,
    borderWidth: 1.5,
    bottom: 3,
    height: 11,
    position: "absolute",
    right: 3,
    width: 11,
  },
  panel: {
    borderRadius: Radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    bottom: 68,
    left: 14,
    maxWidth: 430,
    padding: 12,
    position: "absolute",
    right: 14,
    shadowColor: "#000000",
    shadowOffset: { height: 10, width: 0 },
    shadowOpacity: 0.28,
    shadowRadius: 24,
    zIndex: 30,
  },
  panelHeader: {
    alignItems: "center",
    flexDirection: "row",
    minHeight: 54,
  },
  panelPet: { height: 58, resizeMode: "contain", width: 58 },
  identity: { flex: 1, marginLeft: 8, minWidth: 0 },
  petName: { fontSize: 17, fontWeight: "700", letterSpacing: -0.2 },
  petRole: { fontSize: 12, lineHeight: 16, marginTop: 1 },
  close: {
    alignItems: "center",
    borderRadius: 18,
    height: 36,
    justifyContent: "center",
    marginLeft: 7,
    width: 36,
  },
  statusRow: {
    alignItems: "center",
    flexDirection: "row",
    minHeight: 22,
    paddingHorizontal: 3,
  },
  statusDot: { borderRadius: 4, height: 8, marginRight: 7, width: 8 },
  statusText: { fontSize: 12, fontWeight: "600" },
  picker: { marginHorizontal: -3, marginVertical: 4 },
  pickerContent: { gap: 6, paddingHorizontal: 3 },
  petChoice: {
    alignItems: "center",
    borderRadius: 20,
    borderWidth: 1.5,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  petChoiceImage: { height: 37, resizeMode: "contain", width: 37 },
  composer: {
    alignItems: "flex-end",
    borderRadius: 24,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    minHeight: 48,
    padding: 4,
  },
  input: {
    flex: 1,
    fontSize: 15,
    lineHeight: 20,
    maxHeight: 92,
    minHeight: 40,
    paddingBottom: 9,
    paddingHorizontal: 10,
    paddingTop: 9,
    ...Platform.select({
      web: { outlineStyle: "none" } as never,
      default: {},
    }),
  },
  send: {
    alignItems: "center",
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  pressed: { opacity: 0.58 },
});
